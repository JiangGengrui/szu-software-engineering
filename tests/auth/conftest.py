"""账号与权限模块（AC-01～AC-21、AC-143）的测试固件。

隔离要求：每个用例使用独立的临时实例目录，不读取也不写入仓库内的 ``instance/``。
时间要求：应用内的 ``now()`` 由 ``Clock`` 替换，验证 7 天有效期等边界时不真实等待。
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime

import pytest
from album import create_app
from album.auth import hash_password
from album.models import User, db
from flask import Flask
from support import PASSWORD, Clock


@pytest.fixture()
def clock() -> Clock:
    return Clock()


@pytest.fixture()
def app(tmp_path, clock: Clock) -> Iterator[Flask]:
    application = create_app({
        "INSTANCE_PATH": str(tmp_path / "instance"),
        "SECRET_KEY": "test-signing-key-not-for-runtime",
        "NOW": clock,
        "SEED_ADMIN_PASSWORD": "Admin1234",
        "SEED_USER_PASSWORD": PASSWORD,
        "TESTING": True,
    })
    yield application
    with application.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture()
def client(app: Flask):
    return app.test_client()


@pytest.fixture()
def make_user(app: Flask) -> Callable[..., int]:
    """直接写入账号，用于构造禁用、管理员等前置状态。"""

    def _make(username: str = "student_x", password: str = PASSWORD,
              role: str = "user", status: str = "active") -> int:
        with app.app_context():
            user = User(username=username, password_hash=hash_password(password), role=role,
                        status=status, created_at=datetime(2026, 11, 20, 0, 0, 0))
            db.session.add(user)
            db.session.commit()
            return user.id

    return _make
