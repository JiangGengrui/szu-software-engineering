"""Jinja administration: independent session, CSRF and transactional moderation."""
from datetime import timedelta
from math import ceil
from typing import Any
from urllib.parse import urlencode

from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import false, func, select, update
from werkzeug.datastructures import MultiDict
from werkzeug.security import check_password_hash

from .auth import check_csrf, create_admin_session, require_admin
from .common import (
    MAX_ID,
    BusinessError,
    atomic,
    fail,
    fields,
    iso,
    now,
    paging,
    positive,
    tag_names,
)
from .models import Tag, User, Work, db
from .work import filtered_works, get_work, work_page

bp = Blueprint("admin", __name__, url_prefix="/admin")
USER_FILTERS = {"username", "user_id", "role", "status", "page", "page_size"}
WORK_FILTERS = {"author", "date", "tag", "status", "page", "page_size"}


def admin_identity() -> User:
    user = require_admin()
    g.admin = {"id": user.id, "username": user.username}
    return user


def render_failure(error: BusinessError) -> tuple[str, int]:
    g.business_code = error.code
    # Re-reading an unparsed body can replace the original error with another parse failure.
    parsed_form: MultiDict[str, str] = request.__dict__.get("form", MultiDict())
    if request.path == "/admin/login":
        return render_template("login.html", error=error, username=parsed_form.get("username", "")), error.status
    source = parsed_form if request.method == "POST" else request.args
    endpoint = "admin.works" if "/works" in request.path else "admin.users"
    allowed = WORK_FILTERS if endpoint == "admin.works" else USER_FILTERS
    preserved = [(key, value) for key in allowed for value in source.getlist(key)]
    return render_template("error.html", error=error, preserved=preserved,
                           return_url=url_for(endpoint)), error.status


def require_page_admin() -> User | None:
    try:
        return admin_identity()
    except BusinessError as error:
        if error.code == 2001:
            return None
        raise


@bp.get("/login")
@atomic()
def login_page() -> Any:
    if require_page_admin() is not None:
        return redirect(url_for("admin.users"))
    return render_template("login.html", error=None, username="")


@bp.post("/login")
@atomic(write=True)
def login() -> Any:
    check_csrf()
    values = fields(request.form, {"username", "password", "csrf_token"})
    if not values.get("username") or not values.get("password"):
        fail(1001, "请填写用户名和密码")
    user = db.session.scalar(select(User).where(User.username == values["username"]))
    instant = now()
    if user is not None and user.admin_locked_until is not None:
        if instant < user.admin_locked_until:
            remaining = ceil((user.admin_locked_until - instant).total_seconds())
            fail(1005, f"账号已锁定，请在{remaining}秒后重试")
        user.admin_locked_until, user.admin_failures = None, 0
    stored = user.password_hash if user else current_app.extensions["dummy_password_hash"]
    if not check_password_hash(stored, values["password"]):
        if user is not None:
            user.admin_failures += 1
            if user.admin_failures >= 5:
                user.admin_locked_until = instant + timedelta(seconds=300)
        # Return the error response through the transaction, not an exception: counters COMMIT.
        return render_failure(BusinessError(1007))
    if user is None:
        fail(1007)
    if user.status != "active":
        return render_failure(BusinessError(1008))
    if user.role != "admin":
        return render_failure(BusinessError(2002))
    user.admin_failures, user.admin_locked_until = 0, None
    db.session.flush()
    user_id = user.id
    g.after_commit.append(lambda: create_admin_session(user_id))
    return redirect(url_for("admin.users"), code=303)


@bp.post("/logout")
@atomic(write=True)
def logout() -> Any:
    admin_identity()
    check_csrf()
    fields(request.form, {"csrf_token"})
    def revoke() -> None:
        current_app.extensions["admin_sessions"].pop(session.get("sid"), None)
        session.clear()
    g.after_commit.append(revoke)
    return redirect(url_for("admin.login_page"), code=303)


def user_query(values: dict[str, str]) -> Any:
    statement = select(User)
    if values.get("username"):
        statement = statement.where(func.instr(User.username, values["username"]) > 0)
    if values.get("user_id"):
        uid = positive(values["user_id"])
        statement = statement.where(User.id == uid) if uid <= MAX_ID else statement.where(false())
    for field, choices in (("role", ("user", "admin")), ("status", ("active", "disabled"))):
        if values.get(field):
            if values[field] not in choices:
                fail()
            statement = statement.where(getattr(User, field) == values[field])
    return statement


def links(endpoint: str, values: dict[str, str], tags: list[str], page: int, size: int, total: int) -> dict[str, str | None]:
    pairs = [(k, v) for k, v in values.items() if k not in ("tag", "page")]
    pairs.extend(("tag", name) for name in tags)
    base = url_for(endpoint)
    return {
        "previous": base + "?" + urlencode(pairs + [("page", str(page - 1))]) if page > 1 else None,
        "next": base + "?" + urlencode(pairs + [("page", str(page + 1))]) if page * size < total else None,
    }


@bp.get("/users")
@atomic()
def users() -> Any:
    if require_page_admin() is None:
        return redirect(url_for("admin.login_page"))
    values = fields(request.args, USER_FILTERS)
    page, size = paging(values)
    statement = user_query(values)
    total = db.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    offset = (page - 1) * size
    records = list(db.session.scalars(statement.order_by(User.id.desc()).offset(offset).limit(size))) if offset < total else []
    counts = dict(db.session.execute(select(Work.user_id, func.count(Work.id))
                  .where(Work.user_id.in_([u.id for u in records])).group_by(Work.user_id)).all())
    rows = [{"id": u.id, "username": u.username, "role": u.role, "status": u.status,
             "created_at": iso(u.created_at), "work_count": counts.get(u.id, 0)} for u in records]
    return render_template("users.html", rows=rows, values=values, page=page, total=total,
                           links=links("admin.users", values, [], page, size, total), active="users")


@bp.get("/works")
@atomic()
def works() -> Any:
    if require_page_admin() is None:
        return redirect(url_for("admin.login_page"))
    values = fields(request.args, WORK_FILTERS, {"tag"})
    page, size = paging(values)
    names = tag_names(request.args.getlist("tag"))
    result = work_page(filtered_works(values, names, public=False), page, size, "admin")
    tags = list(db.session.scalars(select(Tag.name).order_by(Tag.name)))
    return render_template("works.html", rows=result["list"], values=values, selected_tags=names,
                           tags=sorted(set(tags + names)), page=page, total=result["total"],
                           links=links("admin.works", values, names, page, size, result["total"]), active="works")


def return_filters(works: bool = False) -> tuple[dict[str, str], list[str]]:
    allowed = WORK_FILTERS if works else USER_FILTERS
    values = fields(request.form, allowed | {"csrf_token"}, {"tag"} if works else set())
    values.pop("csrf_token", None)
    paging(values)
    names = tag_names(request.form.getlist("tag")) if works else []
    if works:
        filtered_works(values, names, public=False)
    else:
        user_query(values)
    return values, names


def return_list(endpoint: str, values: dict[str, str], tags: list[str]) -> Any:
    pairs = [(k, v) for k, v in values.items() if k != "tag"] + [("tag", t) for t in tags]
    return redirect(url_for(endpoint) + ("?" + urlencode(pairs) if pairs else ""), code=303)


@bp.post("/users/<int:user_id>/disable")
@atomic(write=True)
def disable(user_id: int) -> Any:
    admin = admin_identity()
    check_csrf()
    values, tags = return_filters()
    user = db.session.get(User, user_id) if 1 <= user_id <= MAX_ID else None
    if user is None:
        fail(1004)
    if user.id == admin.id or user.role != "user":
        fail(1003, "不能禁用管理员")
    if user.status == "disabled":
        fail(1005)
    user.status = "disabled"
    db.session.execute(update(Work).where(Work.user_id == user.id).values(status="removed", updated_at=now()))
    db.session.flush()
    g.after_commit.append(lambda: flash("用户已禁用，其全部作品已下架。历史评论和评分保留。", "success"))
    return return_list("admin.users", values, tags)


@bp.post("/works/<int:work_id>/remove")
@atomic(write=True)
def remove(work_id: int) -> Any:
    admin_identity()
    check_csrf()
    values, tags = return_filters(works=True)
    work = get_work(work_id, public=False)
    if work.status != "visible":
        fail(1005)
    work.status, work.updated_at = "removed", now()
    db.session.flush()
    g.after_commit.append(lambda: flash("作品已移除。小程序与媒体入口已隐藏，此操作不可恢复。", "success"))
    return return_list("admin.works", values, tags)
