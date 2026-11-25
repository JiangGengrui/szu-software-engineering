"""Work services and explicit, batched public/admin projections."""
import json
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from flask import Blueprint, request
from sqlalchemy import Select, delete, func, select

from .auth import require_user
from .common import (
    MAX_ID,
    activity_date,
    atomic,
    empty_body,
    fail,
    fields,
    iso,
    now,
    ok,
    paging,
    tag_names,
    text,
    today,
)
from .media import move_staged, stage_collection
from .models import Media, Rating, Tag, User, Work, WorkTag, db

bp = Blueprint("work", __name__, url_prefix="/api")


def get_work(work_id: int, public: bool = True) -> Work:
    item = db.session.get(Work, work_id) if 1 <= work_id <= MAX_ID else None
    if item is None:
        fail(1004)
    if public:
        author = db.session.get(User, item.user_id)
        if item.status != "visible" or author is None or author.status != "active":
            fail(1010)
    return item


def owned_work(work_id: int, user: User) -> Work:
    work = get_work(work_id, public=False)
    if work.user_id != user.id:
        fail(1003)
    if work.status != "visible":
        fail(1005)
    return work


def average(total: int, count: int) -> float | None:
    return float((Decimal(total) / count).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)) if count else None


def media_public(item: Media) -> dict[str, Any]:
    return {"id": item.id, "kind": item.kind, "url": f"/media/{item.id}", "mime": item.mime,
            "size_bytes": item.size_bytes, "position": item.position}


def projections(works: list[Work], mode: str = "public", detail: bool = False) -> list[dict[str, Any]]:
    if not works:
        return []
    ids = [w.id for w in works]
    users = {u.id: u for u in db.session.scalars(select(User).where(User.id.in_({w.user_id for w in works})))}
    media: dict[int, list[Media]] = {key: [] for key in ids}
    for item in db.session.scalars(select(Media).where(Media.work_id.in_(ids), Media.active.is_(True)).order_by(Media.position)):
        media[item.work_id].append(item)
    ratings = {wid: (total, count) for wid, total, count in db.session.execute(
        select(Rating.work_id, func.sum(Rating.score), func.count(Rating.id))
        .where(Rating.work_id.in_(ids)).group_by(Rating.work_id)
    )}
    tags: dict[int, list[str]] = {key: [] for key in ids}
    if detail or mode == "admin":
        for wid, name in db.session.execute(select(WorkTag.work_id, Tag.name).join(Tag)
                .where(WorkTag.work_id.in_(ids)).order_by(Tag.name)):
            tags[wid].append(name)
    result: list[dict[str, Any]] = []
    for work in works:
        items, author = media[work.id], users[work.user_id]
        row: dict[str, Any] = {
            "id": work.id, "title": work.title, "summary": work.content[:80],
            "activity_date": work.activity_date.isoformat(), "status": work.status,
        }
        if mode == "admin":
            row.update(user={"id": author.id, "username": author.username}, tags=tags[work.id])
        else:
            row.update(created_at=iso(work.created_at), media_kind=items[0].kind if items else "text",
                       cover_url=f"/media/{items[0].id}" if items and items[0].kind == "image" and work.status == "visible" else None)
            if mode != "mine":
                total, count = ratings.get(work.id, (0, 0))
                row.update(user={"id": author.id, "username": author.username},
                           rating_avg=average(total, count), rating_count=count)
            if detail:
                row.update(content=work.content, tags=tags[work.id], media=[media_public(m) for m in items])
        result.append(row)
    return result


def detail_dto(work: Work) -> dict[str, Any]:
    return projections([work], detail=True)[0]


def tag_filter(statement: Select[Any], names: list[str]) -> Select[Any]:
    if names:
        matching = (select(WorkTag.work_id).join(Tag).where(Tag.name.in_(names))
                    .group_by(WorkTag.work_id).having(func.count(WorkTag.tag_id) == len(names)))
        statement = statement.where(Work.id.in_(matching))
    return statement


def filtered_works(values: dict[str, str], names: list[str], public: bool = True) -> Select[Any]:
    statement = select(Work).join(User)
    if public:
        statement = statement.where(Work.status == "visible", User.status == "active")
    else:
        if values.get("author"):
            # SQLite instr is a literal, case-sensitive substring operation (no LIKE wildcards).
            statement = statement.where(func.instr(User.username, values["author"]) > 0)
        if values.get("status"):
            if values["status"] not in ("visible", "removed"):
                fail()
            statement = statement.where(Work.status == values["status"])
    if values.get("date"):
        statement = statement.where(Work.activity_date == activity_date(values["date"]))
    return tag_filter(statement, names)


def work_page(statement: Select[Any], page: int, size: int, mode: str = "public") -> dict[str, Any]:
    total = db.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    offset = (page - 1) * size
    works = list(db.session.scalars(statement.order_by(Work.created_at.desc(), Work.id.desc()).offset(offset).limit(size))) if offset < total else []
    return {"list": projections(works, mode), "total": total, "page": page, "page_size": size}


def replace_tags(work: Work, names: list[str]) -> None:
    db.session.execute(delete(WorkTag).where(WorkTag.work_id == work.id))
    for name in names:
        tag = db.session.scalar(select(Tag).where(Tag.name == name))
        if tag is None:
            tag = Tag(name=name)
            db.session.add(tag)
            db.session.flush()
        db.session.add(WorkTag(work_id=work.id, tag_id=tag.id))


def save_work(user: User, work: Work | None = None) -> Work:
    if request.mimetype != "multipart/form-data" or request.args:
        fail()
    values = fields(request.form, {"title", "content", "activity_date", "tags"})
    if set(request.files) - {"images", "video"}:
        fail()
    # A malformed body can be decoded as an empty form; it must not become a successful no-op edit.
    if work is not None and not values and not request.files:
        fail()
    # All provided scalar types are checked before field-specific length/date rules.
    for value in values.values():
        text(value)
    title = values.get("title", work.title if work else "")
    content = values.get("content", work.content if work else "").strip()
    if len(title) > 50:
        fail(1001, "标题不能超过50字")
    if len(content) > 2000:
        fail(1012)
    date = activity_date(values["activity_date"], publishing=True) if "activity_date" in values else (work.activity_date if work else today())
    names: list[str] | None = None
    if "tags" in values:
        try:
            raw_tags = json.loads(values["tags"])
        except (ValueError, UnicodeError):
            fail(1013)
        names = tag_names(raw_tags, publishing=True)
    elif work is None:
        names = []
    images, videos = request.files.getlist("images"), request.files.getlist("video")
    retained = list(db.session.scalars(select(Media).where(Media.work_id == work.id, Media.active.is_(True)))) if work else []
    staged = stage_collection(content, images, videos, [] if images or videos else retained)
    if work is None:
        work = Work(user_id=user.id, created_at=now())
        db.session.add(work)
    work.title, work.content, work.activity_date, work.updated_at = title, content, date, now()
    db.session.flush()
    if names is not None:
        replace_tags(work, names)
    if staged:
        for previous in retained:
            previous.active = False
        for position, item in enumerate(staged):
            db.session.add(Media(work_id=work.id, kind=item.kind, file_key=item.key, mime=item.mime,
                                 size_bytes=item.size, position=position, created_at=now()))
    db.session.flush()
    move_staged(staged)
    return work


@bp.get("/works")
@atomic()
def list_works() -> Any:
    values = fields(request.args, {"date", "tag", "page", "page_size"}, {"tag"})
    page, size = paging(values)
    names = tag_names(request.args.getlist("tag"))
    return ok(work_page(filtered_works(values, names), page, size))


@bp.get("/tags")
@atomic()
def list_tags() -> Any:
    fields(request.args, set())
    return ok([{"id": t.id, "name": t.name} for t in db.session.scalars(select(Tag).order_by(Tag.name))])


@bp.get("/works/mine")
@atomic()
def mine() -> Any:
    user = require_user()
    values = fields(request.args, {"page", "page_size"})
    page, size = paging(values)
    return ok(work_page(select(Work).where(Work.user_id == user.id), page, size, "mine"))


@bp.get("/works/<int:work_id>")
@atomic()
def detail(work_id: int) -> Any:
    fields(request.args, set())
    return ok(detail_dto(get_work(work_id)))


@bp.post("/works")
@atomic(write=True)
def publish() -> Any:
    user = require_user()
    return ok(detail_dto(save_work(user)), 201)


@bp.put("/works/<int:work_id>")
@atomic(write=True)
def edit(work_id: int) -> Any:
    user = require_user()
    work = owned_work(work_id, user)
    return ok(detail_dto(save_work(user, work)))


@bp.delete("/works/<int:work_id>")
@atomic(write=True)
def remove(work_id: int) -> Any:
    user = require_user()
    work = owned_work(work_id, user)
    empty_body()
    work.status, work.updated_at = "removed", now()
    return ok({"id": work.id, "status": work.status})
