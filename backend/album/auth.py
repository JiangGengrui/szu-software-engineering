"""Independent ordinary-user tokens and server-revocable administrator sessions."""
import re
import secrets
from datetime import UTC, timedelta
from math import ceil
from typing import Any

from flask import Blueprint, current_app, request, session
from itsdangerous import BadData, TimestampSigner, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from .common import MAX_ID, atomic, empty_body, fail, iso, json_fields, now, ok, text, transaction
from .models import User, db

bp = Blueprint("auth", __name__, url_prefix="/api/auth")
TOKEN_AGE = 604800
LOGIN_FAILURES = 5
LOGIN_LOCK_SECONDS = 300


class ClockSigner(TimestampSigner):
    def get_timestamp(self) -> int:
        return int(now().replace(tzinfo=UTC).timestamp())


def serializer() -> URLSafeTimedSerializer:
    key = current_app.secret_key
    if key is None:
        raise RuntimeError("Signing key not initialized")
    return URLSafeTimedSerializer(key, salt="album-user-token-v1", signer=ClockSigner)


def user_public(user: User) -> dict[str, Any]:
    return {"id": user.id, "username": user.username, "role": user.role}


def issue_token(user: User) -> dict[str, Any]:
    return {
        "user": user_public(user),
        "token": serializer().dumps({"uid": user.id, "token_version": user.token_version}),
        "expires_at": iso(now() + timedelta(seconds=TOKEN_AGE)),
    }


def require_user() -> User:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        fail(1002)
    try:
        data = serializer().loads(header[7:], max_age=TOKEN_AGE - 1)
    except BadData:
        fail(1002)
    if (not isinstance(data, dict) or type(data.get("uid")) is not int
            or type(data.get("token_version")) is not int or not 1 <= data["uid"] <= MAX_ID):
        fail(1002)
    user = db.session.get(User, data["uid"])
    if user is None or user.status != "active" or user.token_version != data["token_version"]:
        fail(1002)
    if user.role != "user":
        fail(1003)
    return user


def validate_username(value: Any) -> str:
    username = text(value)
    if not re.fullmatch(r"[A-Za-z0-9_\u3400-\u4dbf\u4e00-\u9fff\U00020000-\U0002fa1f]{3,20}", username):
        fail(1001, "用户名须为3—20位中英文、数字或下划线")
    return username


def validate_password(value: Any) -> str:
    password = text(value)
    if not 8 <= len(password) <= 20 or not re.search(r"[A-Za-z]", password) or not re.search(r"[0-9]", password):
        fail(1001, "密码须为8—20位且同时包含字母和数字")
    return password


def hash_password(password: str) -> str:
    return generate_password_hash(password, method=current_app.config["PASSWORD_METHOD"])


@bp.post("/register")
def register() -> Any:
    data = json_fields({"username", "password"}, {"username", "password"})
    username = validate_username(data["username"])
    password = validate_password(data["password"])
    # The expensive PBKDF2 call must not hold the process-wide write gate.
    password_hash = hash_password(password)
    with transaction(write=True):
        if db.session.scalar(select(User.id).where(User.username == username)) is not None:
            fail(1006)
        user = User(username=username, password_hash=password_hash, created_at=now())
        db.session.add(user)
        try:
            db.session.flush()
        except IntegrityError as error:
            # The unique constraint remains authoritative even after the friendly precheck.
            if str(error.orig) == "UNIQUE constraint failed: users.username":
                fail(1006)
            raise
        return ok(issue_token(user), 201)


def record_login_failure(user_id: int) -> None:
    with transaction(write=True):
        user = db.session.get(User, user_id)
        if user is None:
            return
        instant = now()
        if user.login_locked_until is not None:
            if instant < user.login_locked_until:
                return
            user.login_failures, user.login_locked_until = 0, None
        user.login_failures += 1
        if user.login_failures >= LOGIN_FAILURES:
            user.login_locked_until = instant + timedelta(seconds=LOGIN_LOCK_SECONDS)


@bp.post("/login")
def login() -> Any:
    data = json_fields({"username", "password"}, {"username", "password"})
    username, password = text(data["username"]), text(data["password"])
    with transaction():
        user = db.session.scalar(select(User).where(User.username == username))
        # Only plain values survive the read transaction; the PBKDF2 call stays outside the gate.
        account = None if user is None else (user.id, user.password_hash, user.status, user.role,
                                             user.login_failures, user.login_locked_until)
        stored = account[1] if account else current_app.extensions["dummy_password_hash"]
    if account is not None and account[5] is not None and now() < account[5]:
        remaining = ceil((account[5] - now()).total_seconds())
        fail(1005, f"账号已锁定，请在{remaining}秒后重试")
    if not check_password_hash(stored, password):
        if account is not None:
            record_login_failure(account[0])
        fail(1007)
    if account is None:
        fail(1007)
    with transaction(write=True):
        user = db.session.get(User, account[0])
        if user is None:
            fail(1007)
        if user.status != "active":
            fail(1008)
        if user.role != "user":
            fail(1003)
        user.login_failures, user.login_locked_until = 0, None
        return ok(issue_token(user))


@bp.get("/me")
@atomic()
def me() -> Any:
    user = require_user()
    if request.args:
        fail()
    return ok(user_public(user))


@bp.post("/password")
@atomic(write=True)
def password_change() -> Any:
    user = require_user()
    data = json_fields({"old_password", "new_password"}, {"old_password", "new_password"})
    old, new = text(data["old_password"]), text(data["new_password"])
    if not check_password_hash(user.password_hash, old):
        fail(1007)
    validate_password(new)
    if new == old:
        fail(1001, "新密码不能与原密码相同")
    user.password_hash = hash_password(new)
    user.token_version += 1
    return ok()


@bp.post("/logout")
@atomic(write=True)
def logout() -> Any:
    user = require_user()
    empty_body()
    user.token_version += 1
    return ok()


def csrf_token() -> str:
    value = session.get("csrf_token")
    if not isinstance(value, str):
        value = secrets.token_urlsafe(32)
        session["csrf_token"] = value
    return value


def check_csrf() -> None:
    expected, supplied = session.get("csrf_token"), request.form.get("csrf_token")
    if (not isinstance(expected, str) or not isinstance(supplied, str)
            or len(request.form.getlist("csrf_token")) != 1
            or not secrets.compare_digest(expected.encode("utf-8"), supplied.encode("utf-8"))):
        fail(1003, "请求校验失败，请刷新页面后重试")


def require_admin() -> User:
    sid = session.get("sid")
    registry = current_app.extensions["admin_sessions"]
    entry = registry.get(sid) if isinstance(sid, str) else None
    instant = now()
    if (entry is None or instant >= entry["expires_at"]
            or instant >= entry.get("absolute_expires_at", entry["expires_at"])):
        if entry is not None:
            registry.pop(sid, None)
        fail(2001)
    user = db.session.get(User, entry["uid"])
    if user is None or user.status != "active":
        fail(2001)
    if user.role != "admin":
        fail(2002)
    # Idle time restarts on every authenticated request, but the issued session still has an absolute cap.
    entry["expires_at"] = instant + timedelta(seconds=current_app.config["ADMIN_SESSION_IDLE"])
    return user


def create_admin_session(user_id: int) -> None:
    registry = current_app.extensions["admin_sessions"]
    previous = session.get("sid")
    if previous:
        registry.pop(previous, None)
    for sid, entry in list(registry.items()):
        if now() >= entry["expires_at"]:
            registry.pop(sid, None)
    session.clear()
    instant = now()
    sid = secrets.token_urlsafe(32)
    registry[sid] = {
        "uid": user_id,
        "issued_at": instant,
        "expires_at": instant + timedelta(seconds=current_app.config["ADMIN_SESSION_IDLE"]),
        "absolute_expires_at": instant + timedelta(seconds=current_app.config["ADMIN_SESSION_ABSOLUTE"]),
    }
    session["sid"] = sid
    session["csrf_token"] = secrets.token_urlsafe(32)
