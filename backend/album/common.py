"""Transport validation, explicit transaction boundaries and safe error contracts."""
import json
import re
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from functools import wraps
from pathlib import Path
from threading import RLock
from typing import Any, NoReturn, ParamSpec, TypeVar

from flask import Response, current_app, g, jsonify, request
from sqlalchemy.exc import IntegrityError, OperationalError
from werkzeug.datastructures import MultiDict

from .models import db

P = ParamSpec("P")
T = TypeVar("T")
WRITE_LOCK = RLock()  # One gate shared by every factory and every write command in this process.
MAX_ID = 2**63 - 1
ERRORS = {
    1001: (400, "参数不合法"), 1002: (401, "请重新登录"),
    1003: (403, "无权限"), 1004: (404, "资源不存在"),
    1005: (409, "状态已改变，请重新查询"), 1006: (400, "用户名已存在"),
    1007: (400, "用户名或密码错误"), 1008: (403, "账号已禁用"),
    1009: (400, "不能给自己的作品评分"), 1010: (404, "作品已移除，无法查看"),
    1011: (400, "正文与媒体不能同时为空"), 1012: (400, "正文不能超过2000字"),
    1013: (400, "标签不合法"), 1014: (400, "图片与视频不能混合"),
    1015: (400, "媒体类型、大小或数量不合法"), 1016: (500, "文件保存失败，请重试"),
    2001: (401, "管理会话已失效，请重新登录"), 2002: (403, "仅管理员可进入"),
}


class BusinessError(Exception):
    def __init__(self, code: int, message: str | None = None) -> None:
        self.code = code
        self.status, default = ERRORS[code]
        self.message = message or default
        super().__init__(self.message)


def fail(code: int = 1001, message: str | None = None) -> NoReturn:
    raise BusinessError(code, message)


def now() -> datetime:
    clock = current_app.config.get("NOW")
    value = clock() if clock else datetime.now(UTC)
    return value.astimezone(UTC).replace(tzinfo=None)


def today() -> date:
    return (now() + timedelta(hours=8)).date()


def iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds") + "Z"


def ok(data: Any = None, status: int = 200) -> tuple[Response, int]:
    return jsonify(code=0, message="ok", data=data), status


def error_json(error: BusinessError) -> tuple[Response, int]:
    g.business_code = error.code
    return jsonify(code=error.code, message=error.message, data=None), error.status


@contextmanager
def transaction(write: bool = False) -> Iterator[None]:
    acquired = False
    committed = False
    new_files: list[Path] = []
    try:
        if write:
            acquired = current_app.extensions["write_lock"].acquire(
                timeout=current_app.config["WRITE_LOCK_TIMEOUT"]
            )
            if not acquired:
                fail(1005, "写入繁忙，请重新查询后重试")
        g.new_files = new_files
        g.after_commit = []
        with db.session.begin():
            yield
        committed = True
        # Non-database success effects must not survive a failed commit.
        for callback in g.after_commit:
            callback()
    except BaseException as exc:
        # Only paths registered by this command are compensated, never historical media.
        for path in reversed(new_files) if not committed else []:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                current_app.logger.error("media_compensation_failed")
        if isinstance(exc, (IntegrityError, OperationalError)):
            raise BusinessError(1005) from None
        raise
    finally:
        if acquired:
            current_app.extensions["write_lock"].release()


def atomic(write: bool = False) -> Callable[[Callable[P, T]], Callable[P, T]]:
    def decorate(function: Callable[P, T]) -> Callable[P, T]:
        @wraps(function)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
            with transaction(write):
                return function(*args, **kwargs)
        return wrapped
    return decorate


def text(value: Any, code: int = 1001) -> str:
    if not isinstance(value, str) or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        fail(code)
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            fail()
        result[key] = value
    return result


def json_body() -> bytes:
    # JSON commands carry only a few scalar fields; the global 100MiB cap must not be reachable here.
    limit = current_app.config.get("MAX_JSON_LENGTH", 64 * 1024)
    declared = request.content_length
    if declared is not None and declared > limit:
        fail()
    raw = request.get_data()
    if len(raw) > limit:
        fail()
    return raw


def json_fields(allowed: set[str], required: set[str] | None = None) -> dict[str, Any]:
    if not request.is_json or request.args:
        fail()
    try:
        data = json.loads(json_body(), object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError):
        fail()
    if not isinstance(data, dict) or set(data) - allowed or (required or set()) - set(data):
        fail()
    return data


def empty_body() -> None:
    if json_body():
        if request.is_json:
            json_fields(set())
        else:
            fail()
    if request.args:
        fail()


def fields(source: MultiDict[str, str], allowed: set[str], repeated: set[str] | None = None) -> dict[str, str]:
    if set(source) - allowed:
        fail()
    for key in source:
        if key not in (repeated or set()) and len(source.getlist(key)) != 1:
            fail()
    return source.to_dict()


def positive(value: str) -> int:
    if not re.fullmatch(r"[0-9]+", value):
        fail()
    try:
        number = int(value)
    except ValueError:
        fail()
    if number < 1:
        fail()
    return number


def paging(values: Mapping[str, str], default: int = 10) -> tuple[int, int]:
    page = positive(values.get("page", "1"))
    size = positive(values.get("page_size", str(default)))
    if size > 20:
        fail()
    return page, size


def activity_date(value: Any, publishing: bool = False) -> date:
    value = text(value)
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        fail(1001, "请填写合法活动日期")
    try:
        result = date.fromisoformat(value)
    except ValueError:
        fail(1001, "请填写合法活动日期")
    if publishing and result > today():
        fail(1001, "活动日期不能晚于北京时间今天")
    return result


def tag_names(value: Any, publishing: bool = False) -> list[str]:
    code = 1013 if publishing else 1001
    if not isinstance(value, list):
        fail(code)
    result: list[str] = []
    for item in value:
        name = clean_tag(text(item, code))
        if not 1 <= len(name) <= 10:
            fail(code, "每个标签须为1—10字")
        if name not in result:
            result.append(name)
    if publishing and len(result) > 5:
        fail(1013, "最多填写5个不同标签")
    return result


TAG_NOISE = re.compile("[\x00-\x08\x0e-\x1f\x7f-\x9f\u00ad\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]")
TAG_SPACE = re.compile("[\t-\r\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+")


def clean_tag(name: str) -> str:
    """Remove invisible/control code points and fold internal whitespace before trim."""
    return TAG_SPACE.sub(" ", TAG_NOISE.sub("", name)).strip()
