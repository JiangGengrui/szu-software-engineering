"""Campus Album application factory. Run as one process, without debug or reloader."""
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Any

from flask import Flask, Response, g, request
from sqlalchemy import event
from werkzeug.exceptions import BadRequest, HTTPException, RequestEntityTooLarge

from . import admin, auth, interaction, media, work
from .common import WRITE_LOCK, BusinessError, error_json
from .models import Base, db
from .seed import init_demo_command


def _configure_sqlite(engine: Any) -> None:
    @event.listens_for(engine, "connect")
    def connect(connection: Any, record: Any) -> None:
        connection.isolation_level = None
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    @event.listens_for(engine, "begin")
    def begin(connection: Any) -> None:
        connection.exec_driver_sql("BEGIN")


def _upgrade_schema() -> None:
    """Add only the columns an existing instance is missing; no row is rewritten or deleted."""
    additions = {
        "users": {"login_failures": "INTEGER NOT NULL DEFAULT 0", "login_locked_until": "DATETIME"},
        "works": {"cover_key": "TEXT", "cover_mime": "VARCHAR", "cover_size": "INTEGER"},
    }
    with db.engine.begin() as connection:
        for table, columns in additions.items():
            present = {row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table})")}
            for name, ddl in columns.items():
                if name not in present:
                    connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def create_app(config: dict[str, Any] | None = None) -> Flask:
    supplied = dict(config or {})
    root = Path(__file__).resolve().parents[2] / "instance"
    instance = Path(supplied.pop("INSTANCE_PATH", os.environ.get("ALBUM_INSTANCE_PATH", str(root)))).resolve()
    app = Flask(__name__, instance_path=str(instance), instance_relative_config=True)
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{(instance / 'album.sqlite3').as_posix()}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        MEDIA_ROOT=str(instance / "media"),
        MAX_CONTENT_LENGTH=100 * 1024 * 1024,
        MAX_FORM_MEMORY_SIZE=100 * 1024 * 1024,
        MAX_FORM_PARTS=1000,
        MAX_JSON_LENGTH=64 * 1024,
        PASSWORD_METHOD="pbkdf2:sha256:600000",
        WRITE_LOCK_TIMEOUT=5.0,
        ADMIN_SESSION_IDLE=1800,
        ADMIN_SESSION_ABSOLUTE=28800,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=False,
        SESSION_COOKIE_NAME="album_admin",
        SEED_ADMIN_PASSWORD=os.environ.get("SEED_ADMIN_PASSWORD"),
        SEED_USER_PASSWORD=os.environ.get("SEED_USER_PASSWORD"),
        DEBUG=False,
    )
    app.config.update(supplied)
    app.debug = False
    with WRITE_LOCK:
        instance.mkdir(parents=True, exist_ok=True)
        Path(app.config["MEDIA_ROOT"]).mkdir(parents=True, exist_ok=True)
        (Path(app.config["MEDIA_ROOT"]) / "tmp").mkdir(parents=True, exist_ok=True)
        if not app.secret_key:
            key_file = instance / "secret.key"
            if not key_file.exists():
                with key_file.open("x", encoding="ascii") as output:
                    output.write(secrets.token_hex(32))
            app.secret_key = key_file.read_text(encoding="ascii").strip()
    app.extensions["write_lock"] = WRITE_LOCK
    app.extensions["admin_sessions"] = {}
    db.init_app(app)
    with app.app_context():
        _configure_sqlite(db.engine)
        with WRITE_LOCK:
            Base.metadata.create_all(db.engine)
            _upgrade_schema()
        app.extensions["dummy_password_hash"] = auth.hash_password(secrets.token_urlsafe(20))
        media.cleanup_orphans()
    for blueprint in (auth.bp, work.bp, interaction.bp, media.bp, admin.bp):
        app.register_blueprint(blueprint)
    app.cli.add_command(init_demo_command)
    app.jinja_env.globals["csrf_token"] = auth.csrf_token
    # Suppress the development server's raw URL log, which includes user-supplied queries.
    logging.getLogger("werkzeug").disabled = True

    @app.before_request
    def begin_request() -> None:
        g.request_id = secrets.token_hex(8)
        g.request_started = time.monotonic()

    @app.after_request
    def finish_request(response: Response) -> Response:
        response.headers["X-Request-ID"] = g.get("request_id", "")
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Media and API payloads stay non-cacheable; admin CSS/JS may be reused briefly.
        if request.path.startswith("/static/") and response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=300"
        else:
            response.headers["Cache-Control"] = "no-store"
        if request.path.startswith("/admin"):
            response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        route = request.url_rule.rule if request.url_rule else "unmatched"
        app.logger.info("request id=%s route=%s status=%s business_code=%s duration_ms=%.1f",
                        g.get("request_id", ""), route, response.status_code,
                        g.get("business_code", 0 if response.status_code < 400 else None),
                        (time.monotonic() - g.get("request_started", time.monotonic())) * 1000)
        return response

    @app.errorhandler(BusinessError)
    def business_error(error: BusinessError) -> Any:
        if request.path.startswith("/admin"):
            return admin.render_failure(error)
        return error_json(error)

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(error: RequestEntityTooLarge) -> Any:
        return business_error(BusinessError(1015, "请求体超过100MiB上限"))

    @app.errorhandler(BadRequest)
    def bad_request(error: BadRequest) -> Any:
        # Malformed/truncated input is not an unknown defect; do not reparse its body.
        return business_error(BusinessError(1001))

    @app.errorhandler(404)
    def not_found(error: HTTPException) -> Any:
        return business_error(BusinessError(1004))

    @app.errorhandler(Exception)
    def unexpected(error: Exception) -> Any:
        if isinstance(error, HTTPException):
            return error
        # Unknown defects are NOT a business/file error and never leak request values/tracebacks.
        if app.testing and app.config.get("PROPAGATE_EXCEPTIONS") is not False:
            raise error
        app.logger.error("unexpected_failure request_id=%s", g.get("request_id", "startup"))
        return Response("服务器内部错误，请联系维护人员。", status=500, content_type="text/plain; charset=utf-8")

    return app
