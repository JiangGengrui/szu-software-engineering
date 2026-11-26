"""AC-13～AC-18：修改密码的校验顺序、凭据替换与旧凭据撤销。"""
from __future__ import annotations

import pytest
from support import PASSWORD, bearer, login, register

NEW_PASSWORD = "Changed2026"


def test_wrong_old_password_keeps_current_password(client, make_user):
    """AC-13：原密码错误时修改失败，旧密码仍可登录。"""
    make_user("student_pw")
    token = login(client, "student_pw")["token"]

    response = client.post("/api/auth/password", headers=bearer(token),
                           json={"old_password": "Wrong1234", "new_password": NEW_PASSWORD})

    assert response.status_code == 400
    assert response.get_json()["code"] == 1007
    assert login(client, "student_pw", PASSWORD)["token"]


@pytest.mark.parametrize("new_password", ["short1", "abcdefgh", "12345678", "B" * 21])
def test_illegal_new_password_keeps_current_password(client, make_user, new_password):
    """AC-14：新密码不满足注册密码规则时修改失败，密码不变。"""
    make_user("student_pw")
    token = login(client, "student_pw")["token"]

    response = client.post("/api/auth/password", headers=bearer(token),
                           json={"old_password": PASSWORD, "new_password": new_password})

    assert response.status_code == 400
    assert response.get_json()["code"] == 1001
    assert login(client, "student_pw", PASSWORD)["token"]


def test_new_password_equal_to_old_is_rejected(client, make_user):
    """AC-15：新密码与原密码相同时修改失败。"""
    make_user("student_pw")
    token = login(client, "student_pw")["token"]

    response = client.post("/api/auth/password", headers=bearer(token),
                           json={"old_password": PASSWORD, "new_password": PASSWORD})

    assert response.status_code == 400
    assert response.get_json()["code"] == 1001


def test_successful_change_replaces_credentials(client, make_user):
    """AC-16：改密后新密码可登录，原密码不可登录。"""
    make_user("student_pw")
    token = login(client, "student_pw")["token"]

    response = client.post("/api/auth/password", headers=bearer(token),
                           json={"old_password": PASSWORD, "new_password": NEW_PASSWORD})

    assert response.status_code == 200
    assert response.get_json()["code"] == 0
    assert login(client, "student_pw", NEW_PASSWORD)["token"]

    stale = client.post("/api/auth/login",
                        json={"username": "student_pw", "password": PASSWORD})
    assert stale.status_code == 400
    assert stale.get_json()["code"] == 1007


def test_change_revokes_every_previous_token(client, make_user):
    """AC-17：改密成功后该用户此前版本的全部凭据失效（含发起改密的那个）。"""
    make_user("student_pw")
    first = login(client, "student_pw")["token"]
    second = login(client, "student_pw")["token"]

    assert client.get("/api/auth/me", headers=bearer(second)).status_code == 200
    response = client.post("/api/auth/password", headers=bearer(first),
                           json={"old_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert response.status_code == 200

    for token in (first, second):
        me = client.get("/api/auth/me", headers=bearer(token))
        assert me.status_code == 401
        assert me.get_json()["code"] == 1002


def test_change_requires_authentication(client, make_user):
    """AC-17：未登录不能修改密码。"""
    make_user("student_pw")

    response = client.post("/api/auth/password",
                           json={"old_password": PASSWORD, "new_password": NEW_PASSWORD})

    assert response.status_code == 401
    assert response.get_json()["code"] == 1002


@pytest.mark.parametrize("payload", [
    {"old_password": PASSWORD},
    {"new_password": NEW_PASSWORD},
    {"old_password": PASSWORD, "new_password": NEW_PASSWORD, "username": "student_pw"},
])
def test_change_rejects_missing_or_extra_fields(client, make_user, payload):
    """参数错误口径：改密只接受 old_password 与 new_password。"""
    make_user("student_pw")
    token = login(client, "student_pw")["token"]

    response = client.post("/api/auth/password", headers=bearer(token), json=payload)

    assert response.status_code == 400
    assert response.get_json()["code"] == 1001


def test_change_then_old_token_cannot_change_again(client, make_user):
    """AC-17：用已失效的凭据再次改密返回 401，不产生 500。"""
    make_user("student_pw")
    token = login(client, "student_pw")["token"]
    client.post("/api/auth/password", headers=bearer(token),
                json={"old_password": PASSWORD, "new_password": NEW_PASSWORD})

    again = client.post("/api/auth/password", headers=bearer(token),
                        json={"old_password": NEW_PASSWORD, "new_password": "Another2026"})

    assert again.status_code == 401
    assert again.get_json()["code"] == 1002


def test_register_token_can_change_password(client):
    """AC-16：注册即得到的凭据同样可用于首次改密。"""
    token = register(client, "student_fresh")["token"]

    response = client.post("/api/auth/password", headers=bearer(token),
                           json={"old_password": PASSWORD, "new_password": NEW_PASSWORD})

    assert response.status_code == 200
    assert login(client, "student_fresh", NEW_PASSWORD)["token"]
