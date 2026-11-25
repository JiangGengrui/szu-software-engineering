"""Comments and unique, updatable ratings share the same write gate as moderation."""
from typing import Any

from flask import Blueprint, request
from sqlalchemy import func, select

from .auth import require_user
from .common import atomic, fail, fields, iso, json_fields, now, ok, paging, text
from .models import Comment, Rating, User, db
from .work import average, get_work

bp = Blueprint("interaction", __name__, url_prefix="/api/works")


def comment_public(comment: Comment, user: User) -> dict[str, Any]:
    return {"id": comment.id, "content": comment.content,
            "display_name": user.username if user.status == "active" else "已注销用户",
            "created_at": iso(comment.created_at)}


def rating_stats(work_id: int, user_id: int) -> dict[str, Any]:
    total, count = db.session.execute(select(func.sum(Rating.score), func.count(Rating.id))
                                     .where(Rating.work_id == work_id)).one()
    mine = db.session.scalar(select(Rating.score).where(Rating.work_id == work_id, Rating.user_id == user_id))
    return {"rating_avg": average(total or 0, count), "rating_count": count, "my_score": mine}


@bp.get("/<int:work_id>/comments")
@atomic()
def comments(work_id: int) -> Any:
    get_work(work_id)
    values = fields(request.args, {"page", "page_size"})
    page, size = paging(values, 20)
    total = db.session.scalar(select(func.count(Comment.id)).where(Comment.work_id == work_id)) or 0
    offset = (page - 1) * size
    rows = db.session.execute(select(Comment, User).join(User).where(Comment.work_id == work_id)
                             .order_by(Comment.created_at.desc(), Comment.id.desc()).offset(offset).limit(size)).all() if offset < total else []
    return ok({"list": [comment_public(c, u) for c, u in rows], "total": total, "page": page, "page_size": size})


@bp.post("/<int:work_id>/comments")
@atomic(write=True)
def add_comment(work_id: int) -> Any:
    user = require_user()
    get_work(work_id)
    data = json_fields({"content"}, {"content"})
    content = text(data["content"]).strip()
    if not 1 <= len(content) <= 500:
        fail(1001, "评论须为1—500字")
    comment = Comment(user_id=user.id, work_id=work_id, content=content, created_at=now())
    db.session.add(comment)
    db.session.flush()
    return ok(comment_public(comment, user), 201)


@bp.get("/<int:work_id>/rating")
@atomic()
def read_rating(work_id: int) -> Any:
    user = require_user()
    get_work(work_id)
    fields(request.args, set())
    return ok(rating_stats(work_id, user.id))


@bp.put("/<int:work_id>/rating")
@atomic(write=True)
def update_rating(work_id: int) -> Any:
    user = require_user()
    work = get_work(work_id)
    data = json_fields({"score"}, {"score"})
    score = data["score"]
    if type(score) is not int or not 1 <= score <= 5:
        fail(1001, "评分须为1—5的整数")
    if work.user_id == user.id:
        fail(1009)
    rating = db.session.scalar(select(Rating).where(Rating.work_id == work_id, Rating.user_id == user.id))
    if rating is None:
        rating = Rating(user_id=user.id, work_id=work_id, created_at=now())
        db.session.add(rating)
    rating.score, rating.updated_at = score, now()
    db.session.flush()
    return ok(rating_stats(work_id, user.id))
