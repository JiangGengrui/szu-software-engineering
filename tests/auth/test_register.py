"""AC-01、AC-03～AC-06：注册的输入规则、唯一性与自动登录凭据。"""
from __future__ import annotations

import pytest
from album.models import User, db
from support import PASSWORD, register


def test_register_creates_normal_user_and_returns_credentials(app, client):
    """AC-01/AC-02：注册产生普通用户，并在同一响应中签发可直接使用的凭据。"""
    data = register(client)

    assert data["user"]["username"] == "student_new"
    assert data["user"]["role"] == "user"
    assert isinstance(data["user"]["id"], int)
    assert data["token"]
    assert data["expires_at"].endswith("Z")

    # AC-02 的服务端前提：返回的凭据无需再次登录即可访问受保护接口。
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {data['token']}"})
    assert me.status_code == 200
    assert me.get_json()["data"]["username"] == "student_new"

    with app.app_context():
        assert db.session.scalar(db.select(User.username)) == "student_new"


@pytest.mark.parametrize("username", [
    "ab",                      # 少于 3 字
    "a" * 21,                  # 多于 20 字
    "李" * 2,                  # 中文按字符计数，同样是 2 字
    "user name",               # 空格不在允许字符集
    "张三!",                    # 标点不在允许字符集
    "user-name",               # 连字符不在允许字符集
    "",                        # 空用户名
])
def test_register_rejects_illegal_usernames(client, username):
    """AC-03：用户名须为 3—20 字中英文、数字或下划线，其余一律参数错误。"""
    response = client.post("/api/auth/register", json={"username": username, "password": PASSWORD})

    assert response.status_code == 400
    assert response.get_json()["code"] == 1001


@pytest.mark.parametrize("username", ["abc", "a" * 20, "张三丰", "student_01", "用户_01"])
def test_register_accepts_boundary_usernames(client, username):
    """AC-03：3 字与 20 字是闭区间边界，中文与下划线均可用。"""
    assert register(client, username=username)["user"]["username"] == username


@pytest.mark.parametrize("password", ["Abc1234", "Abc123456789012345678901"])
def test_register_rejects_out_of_range_password_length(client, password):
    """AC-05：7 位与 21 位都在 8—20 的闭区间之外。"""
    response = client.post("/api/auth/register",
                           json={"username": "student_pw", "password": password})

    assert response.status_code == 400
    assert response.get_json()["code"] == 1001


def test_register_accepts_twenty_character_password(client):
    """AC-05：20 位是上边界，仍应注册成功。"""
    password = "Abc12345678901234567"

    assert len(password) == 20
    assert register(client, "student_pw", password)["token"]


@pytest.mark.parametrize("password", [
    "Abc123",                  # 少于 8 位
    "A" + "b" * 19 + "1",      # 21 位
    "abcdefgh",                # 只有字母
    "12345678",                # 只有数字
    "Abcdefg_",                # 无数字
    "_1234567",                # 无字母
])
def test_register_rejects_illegal_passwords(client, password):
    """AC-05：密码须长度 8—20 位且同时包含字母和数字。"""
    response = client.post("/api/auth/register",
                           json={"username": "student_pw", "password": password})

    assert response.status_code == 400
    assert response.get_json()["code"] == 1001


def test_register_rejects_duplicate_username_without_adding_rows(app, client):
    """AC-04：重复用户名返回 400/1006，用户记录数量不变。"""
    register(client, "student_dup")

    response = client.post("/api/auth/register",
                           json={"username": "student_dup", "password": PASSWORD})

    assert response.status_code == 400
    assert response.get_json()["code"] == 1006
    with app.app_context():
        count = db.session.scalar(db.select(db.func.count()).select_from(User))
    assert count == 1


def test_register_username_comparison_is_case_sensitive(app, client):
    """AC-04/§4.9：用户名区分大小写，Student 与 student 是两个账号。"""
    register(client, "Student")
    register(client, "student")

    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(User)) == 2


@pytest.mark.parametrize("payload", [
    {"username": "student_x"},                                   # 缺少密码
    {"password": PASSWORD},                                      # 缺少用户名
    {"username": "student_x", "password": PASSWORD, "role": "admin"},  # 越权字段
    {"username": "student_x", "password": PASSWORD, "status": "disabled"},
])
def test_register_rejects_missing_or_privileged_fields(client, payload):
    """AC-01/AC-17：请求体只接受 username 与 password，客户端不能自带角色或状态。"""
    response = client.post("/api/auth/register", json=payload)

    assert response.status_code == 400
    assert response.get_json()["code"] == 1001


def test_register_rejects_non_json_body(client):
    """AC-03：非 JSON 请求体按参数错误处理，不产生账号。"""
    response = client.post("/api/auth/register", data="username=a&password=Abc12345")

    assert response.status_code == 400
    assert response.get_json()["code"] == 1001


def test_register_rejects_duplicate_json_keys(client):
    """参数错误口径：同一 JSON 键出现两次按参数不合法处理。"""
    body = '{"username":"a1","username":"a2","password":"' + PASSWORD + '"}'
    response = client.post("/api/auth/register", data=body,
                           content_type="application/json")

    assert response.status_code == 400
    assert response.get_json()["code"] == 1001
