"""AC-10、AC-11、AC-19、AC-20：凭据有效期、格式校验与服务端撤销。"""
from __future__ import annotations

import pytest
from album.auth import issue_token, serializer
from album.models import User, db
from support import bearer, login, register

SEVEN_DAYS = 604800


def test_expires_at_is_exactly_seven_days_after_issue(client):
    """AC-10：签发的有效期字段等于签发时刻 + 7 天。"""
    data = register(client)

    assert data["expires_at"] == "2026-12-03T08:00:00Z"


def test_token_still_valid_one_second_before_expiry(client, clock):
    """AC-10：第 604799 秒仍被接受。"""
    token = register(client)["token"]

    clock.advance(SEVEN_DAYS - 1)

    assert client.get("/api/auth/me", headers=bearer(token)).status_code == 200


def test_token_rejected_at_exactly_seven_days(client, clock):
    """AC-10：满 604800 秒不再被接受，返回 401/1002。"""
    token = register(client)["token"]

    clock.advance(SEVEN_DAYS)

    response = client.get("/api/auth/me", headers=bearer(token))
    assert response.status_code == 401
    assert response.get_json()["code"] == 1002


def test_token_issued_before_start_of_clock_is_rejected(client, clock):
    """AC-10：时间回拨不能延长凭据寿命（签名时间晚于当前时间按无效处理）。"""
    token = register(client)["token"]

    clock.advance(-60)

    assert client.get("/api/auth/me", headers=bearer(token)).status_code == 401


@pytest.mark.parametrize("header", [
    "",
    "Bearer",
    "Bearer ",
    "Token abc.def.ghi",
    "bearer lowercase-prefix-is-rejected",
    "Bearer not-a-signed-value",
])
def test_malformed_authorization_header_is_rejected(client, header):
    """AC-10：Authorization 必须为 ``Bearer <签名凭据>``。"""
    headers = {"Authorization": header} if header else {}

    response = client.get("/api/auth/me", headers=headers)

    assert response.status_code == 401
    assert response.get_json()["code"] == 1002


def test_tampered_token_is_rejected(client):
    """AC-10：改动签名字符即失效，不能靠改载荷延长有效期。"""
    token = register(client)["token"]
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")

    assert client.get("/api/auth/me", headers=bearer(tampered)).status_code == 401


def test_token_for_unknown_user_is_rejected(client, app):
    """AC-10：签名正确但用户不存在，凭据仍无效。"""
    with app.app_context():
        token = serializer().dumps({"uid": 999999, "token_version": 0})

    response = client.get("/api/auth/me", headers=bearer(token))

    assert response.status_code == 401
    assert response.get_json()["code"] == 1002


@pytest.mark.parametrize("payload", [
    {"uid": "1", "token_version": 0},
    {"uid": True, "token_version": 0},
    {"uid": 1},
    {"token_version": 0},
    {"uid": 0, "token_version": 0},
    {"uid": 2**63, "token_version": 0},
    ["uid", 1],
])
def test_token_with_invalid_claims_is_rejected(client, app, payload):
    """AC-10：载荷类型与取值范围在验签后仍需校验，非正整数一律拒绝。"""
    with app.app_context():
        token = serializer().dumps(payload)

    response = client.get("/api/auth/me", headers=bearer(token))

    assert response.status_code == 401
    assert response.get_json()["code"] == 1002


def test_token_version_mismatch_is_rejected(client, app, make_user):
    """AC-17/AC-19：服务端版本号变化后旧凭据立即失效。"""
    user_id = make_user("student_ver")
    token = login(client, "student_ver")["token"]

    with app.app_context():
        user = db.session.get(User, user_id)
        assert user is not None
        user.token_version += 1
        db.session.commit()

    response = client.get("/api/auth/me", headers=bearer(token))
    assert response.status_code == 401
    assert response.get_json()["code"] == 1002


def test_disabled_account_loses_session_immediately(client, app, make_user):
    """AC-09/AC-20：禁用即时生效，无需等待凭据过期。"""
    user_id = make_user("student_disabled")
    token = login(client, "student_disabled")["token"]
    assert client.get("/api/auth/me", headers=bearer(token)).status_code == 200

    with app.app_context():
        user = db.session.get(User, user_id)
        assert user is not None
        user.status = "disabled"
        db.session.commit()

    response = client.get("/api/auth/me", headers=bearer(token))
    assert response.status_code == 401
    assert response.get_json()["code"] == 1002


def test_admin_token_is_not_accepted_by_miniprogram_api(client, app, make_user):
    """AC-17/N-04：管理员身份不能通过小程序接口提权。"""
    user_id = make_user("admin_token", role="admin")

    # 直接签发管理员版本的凭据，验证 require_user 的角色分支。
    with app.app_context():
        user = db.session.get(User, user_id)
        assert user is not None
        token = issue_token(user)["token"]

    response = client.get("/api/auth/me", headers=bearer(token))
    assert response.status_code == 403
    assert response.get_json()["code"] == 1003


def test_me_rejects_query_string(client):
    """AC-07/参数错误口径：/me 不接受查询参数。"""
    token = register(client)["token"]

    response = client.get("/api/auth/me?user_id=1", headers=bearer(token))

    assert response.status_code == 400
    assert response.get_json()["code"] == 1001


def test_logout_revokes_all_tokens_of_previous_version(client):
    """AC-19：退出后同一版本签发的其他凭据全部失效。"""
    register(client, "student_out")
    first = login(client, "student_out")["token"]
    second = login(client, "student_out")["token"]

    assert client.post("/api/auth/logout", headers=bearer(first)).status_code == 200

    for token in (first, second):
        assert client.get("/api/auth/me", headers=bearer(token)).status_code == 401


def test_new_login_after_logout_still_works(client):
    """AC-19/AC-20：退出只作废旧版本，重新登录后获得新凭据。"""
    register(client, "student_relogin")
    first = login(client, "student_relogin")["token"]
    client.post("/api/auth/logout", headers=bearer(first))

    second = login(client, "student_relogin")["token"]

    assert second != first
    assert client.get("/api/auth/me", headers=bearer(second)).status_code == 200
