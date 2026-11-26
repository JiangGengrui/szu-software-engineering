"""AC-07～AC-09、AC-21：登录的凭据校验、状态校验与错误口径。"""
from __future__ import annotations

import pytest
from support import PASSWORD, bearer, login, register


def test_login_returns_user_identity_and_token(client, make_user):
    """AC-07：登录成功返回用户 id、username、role 与可用凭据。"""
    user_id = make_user("student_login")

    data = login(client, "student_login")

    assert data["user"] == {"id": user_id, "username": "student_login", "role": "user"}
    assert data["token"]
    assert data["expires_at"].endswith("Z")
    assert client.get("/api/auth/me", headers=bearer(data["token"])).status_code == 200


def test_wrong_password_and_unknown_username_are_indistinguishable(client, make_user):
    """AC-08：不存在用户名与密码错误均返回 400/1007，且提示文字完全相同。"""
    make_user("student_login")

    wrong_password = client.post("/api/auth/login",
                                 json={"username": "student_login", "password": "Wrong1234"})
    unknown_user = client.post("/api/auth/login",
                               json={"username": "nobody_here", "password": "Wrong1234"})

    assert wrong_password.status_code == unknown_user.status_code == 400
    assert wrong_password.get_json() == unknown_user.get_json()
    assert wrong_password.get_json()["code"] == 1007
    assert wrong_password.get_json()["data"] is None


def test_disabled_user_with_correct_password_is_forbidden(client, make_user):
    """AC-09：状态为 disabled 的账号即使密码正确也不能登录，返回 403/1008。"""
    make_user("student_off", status="disabled")

    response = client.post("/api/auth/login",
                           json={"username": "student_off", "password": PASSWORD})

    assert response.status_code == 403
    assert response.get_json()["code"] == 1008


def test_disabled_user_with_wrong_password_reports_credential_error(client, make_user):
    """AC-08/AC-09：先校验凭据再校验状态，避免用 1008 反推账号存在。"""
    make_user("student_off", status="disabled")

    response = client.post("/api/auth/login",
                           json={"username": "student_off", "password": "Wrong1234"})

    assert response.status_code == 400
    assert response.get_json()["code"] == 1007


def test_admin_cannot_log_in_through_miniprogram(client, make_user):
    """AC-07/AC-17 边界：管理员只在 /admin/login 登录，小程序不接受管理员凭据。"""
    make_user("admin_at_api", role="admin")

    response = client.post("/api/auth/login",
                           json={"username": "admin_at_api", "password": PASSWORD})

    assert response.status_code == 403
    assert response.get_json()["code"] == 1003


@pytest.mark.parametrize("payload", [
    {"username": "student_login"},
    {"password": PASSWORD},
    {"username": "student_login", "password": PASSWORD, "role": "admin"},
])
def test_login_rejects_missing_or_privileged_fields(client, make_user, payload):
    """参数错误口径：登录只接受 username 与 password，不能通过请求体提权。"""
    make_user("student_login")

    response = client.post("/api/auth/login", json=payload)

    assert response.status_code == 400
    assert response.get_json()["code"] == 1001


def test_repeated_logout_never_returns_server_error(client):
    """AC-21：已退出状态再次退出返回 401/1002，不产生 500。"""
    token = register(client)["token"]

    first = client.post("/api/auth/logout", headers=bearer(token))
    second = client.post("/api/auth/logout", headers=bearer(token))

    assert first.status_code == 200
    assert first.get_json()["code"] == 0
    assert second.status_code == 401
    assert second.get_json()["code"] == 1002


def test_logout_requires_valid_token(client):
    """AC-19/AC-21：无凭据或伪造凭据的退出按 401/1002 处理。"""
    for headers in ({}, {"Authorization": "Bearer forged-token-value"}):
        response = client.post("/api/auth/logout", headers=headers)
        assert response.status_code == 401
        assert response.get_json()["code"] == 1002
