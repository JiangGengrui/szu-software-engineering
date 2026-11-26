"""账号与权限用例共用的常量与请求助手（不依赖 pytest）。"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

START = datetime(2026, 11, 26, 8, 0, 0, tzinfo=UTC)
PASSWORD = "Student1234"


class Clock:
    """可推进的受控时钟，对应应用工厂的 ``NOW`` 配置项。"""

    def __init__(self, start: datetime = START) -> None:
        self.current = start

    def __call__(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current = self.current + timedelta(seconds=seconds)


def register(client, username: str = "student_new", password: str = PASSWORD) -> dict:
    """注册并返回统一响应壳中的 data。"""
    response = client.post("/api/auth/register",
                           json={"username": username, "password": password})
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()["data"]


def login(client, username: str, password: str = PASSWORD) -> dict:
    """登录并返回统一响应壳中的 data。"""
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()["data"]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
