"""Bounded uploads and guarded media delivery; no decoder or external service."""
import os
import re
import struct
import time
import uuid
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flask import Blueprint, current_app, g, request, send_file
from sqlalchemy import select
from werkzeug.datastructures import FileStorage

from .auth import require_user
from .common import MAX_ID, atomic, fail, fields, ok, transaction
from .models import Media, User, Work, db

bp = Blueprint("media", __name__)
IMAGE_LIMIT = 10 * 1024 * 1024
VIDEO_LIMIT = 50 * 1024 * 1024
COVER_LIMIT = 512 * 1024
STAGE_TTL = 3600
KEY = re.compile(r"(?:u[0-9]{1,19}-)?[0-9a-f]{32}\.(?:png|jpg|mp4)")
STAGED_KEY = re.compile(r"u([0-9]{1,19})-([0-9a-f]{32})\.(png|jpg|mp4)")
TMP_KEY = re.compile(r"[0-9a-f]{32}\.part")


def valid_png(data: bytes) -> bool:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return False
    offset, seen_header, seen_data, ended_data = 8, False, False, False
    started_data, seen_palette, palette_closed = False, False, False
    depth, color = 0, 0
    while offset + 12 <= len(data):
        size = int.from_bytes(data[offset:offset + 4], "big")
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + size
        if size > 0x7FFFFFFF or end > len(data) or not re.fullmatch(rb"[A-Za-z]{2}[A-Z][A-Za-z]", kind):
            return False
        payload = data[offset + 8:end - 4]
        if zlib.crc32(kind + payload) != int.from_bytes(data[end - 4:end], "big"):
            return False
        if not seen_header and kind != b"IHDR":
            return False
        if started_data and kind != b"IDAT":
            ended_data = True
        if kind == b"IHDR":
            if seen_header or size != 13:
                return False
            width, height, depth, color, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
            if (not 1 <= width <= 0x7FFFFFFF or not 1 <= height <= 0x7FFFFFFF
                    or depth not in depths.get(color, set())
                    or compression != 0 or filtering != 0 or interlace not in (0, 1)):
                return False
            seen_header = True
        elif kind == b"PLTE":
            if (seen_palette or started_data or palette_closed or color in (0, 4)
                    or not 0 < size <= 768 or size % 3
                    or (color == 3 and size // 3 > 2 ** depth)):
                return False
            seen_palette = True
        elif kind == b"IDAT":
            if ended_data or (color == 3 and not seen_palette):
                return False
            # Even an empty IDAT starts the one contiguous IDAT sequence.
            started_data = True
            seen_data = seen_data or size > 0
        elif kind == b"IEND":
            return size == 0 and seen_data and end == len(data)
        elif kind[0] < ord("a"):
            # These are the only four PNG critical chunks this validator understands.
            return False
        elif kind in (b"tRNS", b"bKGD", b"hIST"):
            if started_data or (not seen_palette and (color == 3 or kind == b"hIST")):
                return False
            palette_closed = True
        offset = end
    return False


def valid_jpeg(data: bytes) -> bool:
    if not data.startswith(b"\xff\xd8"):
        return False
    offset, frame_marker = 2, 0
    frame_components: set[int] = set()
    scanned_components: set[int] = set()
    while offset < len(data):
        if data[offset] != 0xFF:
            return False
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            return False
        marker = data[offset]
        offset += 1
        if marker == 0xD9:
            return bool(frame_components) and scanned_components == frame_components and offset == len(data)
        if marker in (0, 0xD8) or 0xD0 <= marker <= 0xD7:
            return False
        if offset + 2 > len(data):
            return False
        size = int.from_bytes(data[offset:offset + 2], "big")
        if size < 2 or offset + size > len(data):
            return False
        payload = data[offset + 2:offset + size]
        if marker in (0xC0, 0xC1, 0xC2):
            if frame_marker or size < 11 or payload[1:3] == b"\x00\x00" or payload[3:5] == b"\x00\x00":
                return False
            components = payload[5]
            if (components not in (1, 3, 4) or size != 8 + 3 * components
                    or payload[0] not in ((8,) if marker == 0xC0 else (8, 12))):
                return False
            frame_components = set(payload[6::3])
            if len(frame_components) != components:
                return False
            for i in range(6, len(payload), 3):
                sampling = payload[i + 1]
                if not 1 <= sampling >> 4 <= 4 or not 1 <= sampling & 15 <= 4 or payload[i + 2] > 3:
                    return False
            frame_marker = marker
        elif marker in (0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            return False  # Unsupported frame modes must not hide beside a supported SOF.
        offset += size
        if marker == 0xDA:
            if not frame_marker or size < 8:
                return False
            components = payload[0]
            if not 1 <= components <= 4 or size != 6 + 2 * components:
                return False
            scan_components = set(payload[1:1 + 2 * components:2])
            if len(scan_components) != components or not scan_components <= frame_components:
                return False
            if any(selector >> 4 > 3 or selector & 15 > 3 for selector in payload[2:1 + 2 * components:2]):
                return False
            start, end, approximation = payload[-3:]
            high, low = approximation >> 4, approximation & 15
            if frame_marker == 0xC2:
                if (not 0 <= start <= end <= 63 or (start == 0 and end != 0)
                        or (start > 0 and components != 1) or high > 13 or low > 13
                        or (high != 0 and high != low + 1)):
                    return False
            elif (start, end, approximation) != (0, 63, 0):
                return False
            scan_data = False
            # Entropy bytes may contain stuffed FF00 or restart markers, not arbitrary segments.
            # Jumping to the next 0xFF keeps this linear on multi-megabyte scans instead of
            # visiting every byte of a real photo in Python.
            while offset < len(data):
                if data[offset] != 0xFF:
                    next_marker = data.find(b"\xff", offset)
                    if next_marker < 0:
                        return False
                    scan_data = True
                    offset = next_marker
                    continue
                if offset + 1 >= len(data):
                    return False
                next_byte = data[offset + 1]
                if next_byte == 0:
                    scan_data = True
                    offset += 2
                    continue
                if 0xD0 <= next_byte <= 0xD7:
                    if not scan_data:
                        return False
                    offset += 2
                    continue
                break
            if not scan_data:
                return False
            scanned_components.update(scan_components)
    return False


def _boxes(data: bytes, start: int, end: int, depth: int = 0) -> list[tuple[bytes, int, int]] | None:
    if depth > 16:
        return None
    result: list[tuple[bytes, int, int]] = []
    while start < end:
        if end - start < 8:
            return None
        size = int.from_bytes(data[start:start + 4], "big")
        kind = data[start + 4:start + 8]
        header = 8
        if size == 1:
            if end - start < 16:
                return None
            size = int.from_bytes(data[start + 8:start + 16], "big")
            header = 16
        elif size == 0:
            size = end - start
        if size < header or start + size > end:
            return None
        body, finish = start + header, start + size
        if kind in (b"moov", b"trak", b"mdia", b"minf", b"stbl", b"edts", b"dinf", b"mvex", b"moof", b"traf"):
            children = _boxes(data, body, finish, depth + 1)
            if not children:
                return None
        result.append((kind, body, finish))
        start = finish
    return result


def valid_mp4(data: bytes) -> bool:
    boxes = _boxes(data, 0, len(data))
    if not boxes:
        return False
    ftyp = [item for item in boxes if item[0] == b"ftyp"]
    if len(ftyp) != 1 or boxes[0][0] != b"ftyp":
        return False
    _, start, end = ftyp[0]
    if end - start < 8 or (end - start) % 4:
        return False
    brands = {data[start:start + 4]} | {data[i:i + 4] for i in range(start + 8, end, 4)}
    if not brands & {b"isom", b"iso2", b"iso3", b"iso4", b"iso5", b"iso6", b"mp41", b"mp42", b"avc1", b"M4V "}:
        return False
    return any(k == b"moov" for k, _, _ in boxes) and any(k == b"mdat" and b > a for k, a, b in boxes)


def media_root() -> Path:
    return Path(current_app.config["MEDIA_ROOT"]).resolve()


def controlled_path(key: str) -> Path:
    if not KEY.fullmatch(key):
        fail(1004)
    root = media_root()
    target = (root / key).resolve()
    if target.parent != root:
        fail(1004)
    return target


@dataclass
class StagedMedia:
    temporary: Path
    destination: Path
    key: str
    kind: str
    mime: str
    size: int


MIMES = {"png": "image/png", "jpg": "image/jpeg", "mp4": "video/mp4"}
SPECS = {
    ".png": ("image", "image/png", valid_png, ".png"),
    ".jpg": ("image", "image/jpeg", valid_jpeg, ".jpg"),
    ".jpeg": ("image", "image/jpeg", valid_jpeg, ".jpg"),
    ".mp4": ("video", "video/mp4", valid_mp4, ".mp4"),
}


def stage_file(upload: FileStorage, kind: str, position: int) -> StagedMedia:
    filename = upload.filename or ""
    suffix = Path(filename.replace("\\", "/")).suffix.lower()
    label = f"第{position + 1}个{'图片' if kind == 'image' else '视频'}"
    spec = SPECS.get(suffix)
    if spec is None or spec[0] != kind or upload.mimetype != spec[1]:
        fail(1015, label + "：后缀与媒体类型不匹配")
    identifier = uuid.uuid4().hex
    temporary = media_root() / "tmp" / (identifier + ".part")
    key = identifier + spec[3]
    destination = controlled_path(key)
    limit = IMAGE_LIMIT if kind == "image" else VIDEO_LIMIT
    size = 0
    # UUID collisions must fail without overwriting or compensating an existing file.
    if destination.exists():
        fail(1016)
    try:
        with temporary.open("xb") as output:
            g.new_files.append(temporary)
            while chunk := upload.stream.read(64 * 1024):
                size += len(chunk)
                if size > limit:
                    fail(1015, label + "：文件超出大小上限")
                output.write(chunk)
        data = temporary.read_bytes()
    except OSError:
        fail(1016)
    if size == 0 or not spec[2](data):
        fail(1015, label + "：文件头或容器结构不合法")
    return StagedMedia(temporary, destination, key, kind, spec[1], size)


def stage_collection(content: str, images: list[FileStorage], videos: list[FileStorage], retained: list[Media]) -> list[StagedMedia]:
    # A/B/C/D are intentionally short-circuited in this exact order.
    if not content and not images and not videos and not retained:
        fail(1011)
    if images and videos:
        fail(1014)
    if len(images) > 9:
        fail(1015, "图片最多9张")
    staged = [stage_file(upload, "image", i) for i, upload in enumerate(images)]
    if len(videos) > 1:
        fail(1015, "视频最多1个")
    staged.extend(stage_file(upload, "video", i) for i, upload in enumerate(videos))
    return staged


def move_staged(staged: list[StagedMedia]) -> None:
    for item in staged:
        if item.destination.exists():
            fail(1016)
        g.new_files.append(item.destination)
        try:
            os.replace(item.temporary, item.destination)
        except OSError:
            fail(1016)


def staged_upload(user_id: int, upload: FileStorage) -> dict[str, Any]:
    """Validate one file and keep it under a key that only its uploader may reference later."""
    filename = upload.filename or ""
    spec = SPECS.get(Path(filename.replace("\\", "/")).suffix.lower())
    if spec is None or upload.mimetype != spec[1]:
        fail(1015, "后缀与媒体类型不匹配")
    key = f"u{user_id}-{uuid.uuid4().hex}{spec[3]}"
    destination = controlled_path(key)
    limit = IMAGE_LIMIT if spec[0] == "image" else VIDEO_LIMIT
    size = 0
    if destination.exists():
        fail(1016)
    try:
        with destination.open("xb") as output:
            g.new_files.append(destination)
            while chunk := upload.stream.read(64 * 1024):
                size += len(chunk)
                if size > limit:
                    fail(1015, "文件超出大小上限")
                output.write(chunk)
        data = destination.read_bytes()
    except OSError:
        fail(1016)
    if size == 0 or not spec[2](data):
        fail(1015, "文件头或容器结构不合法")
    return {"key": key, "kind": spec[0], "mime": spec[1], "size_bytes": size}


def staged_media(user_id: int, key: str) -> tuple[str, str, str, int]:
    match = STAGED_KEY.fullmatch(key)
    if match is None or int(match[1]) != user_id:
        fail(1015, "媒体引用无效，请重新上传")
    path = controlled_path(key)
    if not path.is_file():
        fail(1015, "媒体引用不存在或已过期，请重新上传")
    try:
        size = path.stat().st_size
    except OSError:
        fail(1016)
    kind = "video" if match[3] == "mp4" else "image"
    if not 0 < size <= (VIDEO_LIMIT if kind == "video" else IMAGE_LIMIT):
        fail(1015, "媒体文件超出大小上限")
    if db.session.scalar(select(Media.id).where(Media.file_key == key)) is not None:
        fail(1005, "媒体引用已被使用，请重新上传")
    return kind, MIMES[match[3]], key, size


def staged_cover(user_id: int, key: str) -> tuple[str, str, int]:
    match = STAGED_KEY.fullmatch(key)
    if match is None or int(match[1]) != user_id or match[3] == "mp4":
        fail(1015, "封面引用无效，请重新上传")
    path = controlled_path(key)
    if not path.is_file():
        fail(1015, "封面引用不存在或已过期，请重新上传")
    try:
        size = path.stat().st_size
    except OSError:
        fail(1016)
    if not 0 < size <= COVER_LIMIT:
        fail(1015, "封面不能超过512KB")
    return key, MIMES[match[3]], size


def cleanup_orphans() -> None:
    """Called before serving, with the same gate; all historical rows count as references."""
    with transaction(write=True):
        referenced = set(db.session.scalars(select(Media.file_key)))
        referenced |= {key for key in db.session.scalars(select(Work.cover_key)) if key}
        root = media_root()
        candidates = [p for p in (root / "tmp").iterdir() if TMP_KEY.fullmatch(p.name)]
        cutoff = time.time() - STAGE_TTL
        for path in root.iterdir():
            if path.name in referenced or not path.is_file() or path.is_symlink():
                continue
            if STAGED_KEY.fullmatch(path.name):
                # An unreferenced upload may belong to a request that is still publishing.
                try:
                    if path.stat().st_mtime > cutoff:
                        continue
                except OSError:
                    continue
            elif not KEY.fullmatch(path.name):
                continue
            candidates.append(path)
        for path in candidates:
            if path.is_file() and not path.is_symlink():
                try:
                    path.unlink()
                except OSError:
                    current_app.logger.error("media_orphan_cleanup_failed")


@bp.post("/api/uploads")
@atomic(write=True)
def upload() -> Any:
    user = require_user()
    if request.args or request.mimetype != "multipart/form-data":
        fail()
    fields(request.form, set())
    if set(request.files) != {"file"} or len(request.files.getlist("file")) != 1:
        fail()
    return ok(staged_upload(user.id, request.files["file"]), 201)


@bp.route("/media/cover/<int:work_id>", methods=["GET", "HEAD"])
def serve_cover(work_id: int) -> Any:
    with transaction():
        work = db.session.get(Work, work_id) if 1 <= work_id <= MAX_ID else None
        if work is None or not work.cover_key:
            fail(1004)
        author = db.session.get(User, work.user_id)
        if work.status != "visible" or author is None or author.status != "active":
            fail(1010)
        path, mime = controlled_path(work.cover_key), work.cover_mime or "application/octet-stream"
        if not path.is_file():
            fail(1004)
    try:
        response = send_file(path, mimetype=mime, conditional=True, etag=False, max_age=0)
    except OSError:
        fail(1004)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@bp.route("/media/<int:media_id>", methods=["GET", "HEAD"])
def serve(media_id: int) -> Any:
    with transaction():
        row = db.session.execute(
            select(Media, Work, User)
            .select_from(Media)
            .join(Work, Media.work_id == Work.id, isouter=True)
            .join(User, Work.user_id == User.id, isouter=True)
            .where(Media.id == media_id)
        ).first() if 1 <= media_id <= MAX_ID else None
        if row is None:
            fail(1004)
        item, work, author = row
        if not item.active or work is None or work.status != "visible" or author is None or author.status != "active":
            fail(1010)
        path, mime = controlled_path(item.file_key), item.mime
        if not path.is_file():
            fail(1004)
    # Connection released before streaming, including video Range responses.
    try:
        response = send_file(path, mimetype=mime, conditional=True, etag=False, max_age=0)
    except OSError:
        fail(1004)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
