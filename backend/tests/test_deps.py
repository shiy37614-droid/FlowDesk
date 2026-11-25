
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

import app.api.deps as deps

from app.api.deps import get_current_user
from app.db.session import get_db
from app.main import app
from app.models import User


# ============================================
# 1. 模拟数据库
# ============================================

class FakeDB:

    def __init__(self, user=None):
        self.user = user
        self.lookup = None

    def get(self, model, user_id):

        self.lookup = (model, user_id)

        if (
            self.user is not None
            and self.user.id == user_id
        ):
            return self.user

        return None


# ============================================
# 2. 模拟用户
# ============================================

def fake_user():

    now = datetime(
        2026, 11, 23,
        tzinfo=timezone.utc,
    )

    return SimpleNamespace(
        id=5,
        username="zhangsan",
        display_name="张三",
        role_id=6,
        created_at=now,
        updated_at=now,
        password_hash="must-not-leak",
    )


def bearer(token="signed-token"):

    return HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=token,
    )


# ============================================
# 3. 测试有效 Token
# ============================================

def test_valid_token_returns_user(monkeypatch):

    monkeypatch.setattr(
        deps,
        "decode_access_token",
        lambda token: {"sub": "5"},
    )

    user = fake_user()
    db = FakeDB(user)

    result = get_current_user(
        bearer(),
        db,
    )

    assert result is user
    assert db.lookup == (User, 5)


# ============================================
# 4. 测试没有携带 Token
# ============================================

def test_missing_credentials_returns_401():

    with pytest.raises(HTTPException) as exc:

        get_current_user(
            None,
            FakeDB(fake_user()),
        )

    assert exc.value.status_code == 401

    assert exc.value.headers["WWW-Authenticate"] == "Bearer"


# ============================================
# 5. 测试无效 Token
# ============================================

def test_invalid_token_returns_401(monkeypatch):

    monkeypatch.setattr(
        deps,
        "decode_access_token",
        lambda token: None,
    )

    with pytest.raises(HTTPException) as exc:

        get_current_user(
            bearer("bad-token"),
            FakeDB(fake_user()),
        )

    assert exc.value.status_code == 401


# ============================================
# 6. 测试非法用户 ID
# ============================================

@pytest.mark.parametrize(
    "subject",
    [
        "abc",
        "",
        "0",
        "-1",
        "1.5",
        "５",
    ],
)
def test_invalid_subject_returns_401(
    monkeypatch,
    subject,
):

    monkeypatch.setattr(
        deps,
        "decode_access_token",
        lambda token: {"sub": subject},
    )

    db = FakeDB(fake_user())

    with pytest.raises(HTTPException) as exc:

        get_current_user(
            bearer(),
            db,
        )

    assert exc.value.status_code == 401

    # 非法用户 ID 不应该查询数据库
    assert db.lookup is None


# ============================================
# 7. 测试用户不存在
# ============================================

def test_user_not_found_returns_401(monkeypatch):

    monkeypatch.setattr(
        deps,
        "decode_access_token",
        lambda token: {"sub": "5"},
    )

    with pytest.raises(HTTPException) as exc:

        get_current_user(
            bearer(),
            FakeDB(),
        )

    assert exc.value.status_code == 401


# ============================================
# 8. API 集成测试客户端
# ============================================

@pytest.fixture
def api_client(monkeypatch):

    old_overrides = app.dependency_overrides.copy()

    db = FakeDB(fake_user())

    app.dependency_overrides[get_db] = lambda: db

    monkeypatch.setattr(
        deps,
        "decode_access_token",
        lambda token: {"sub": "5"},
    )

    try:

        with TestClient(app) as client:
            yield client

    finally:

        app.dependency_overrides.clear()
        app.dependency_overrides.update(old_overrides)


# ============================================
# 9. 测试 /me 接口
# ============================================

def test_me_endpoint_with_bearer_token(api_client):

    response = api_client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": "Bearer valid-token"
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["id"] == 5
    assert body["username"] == "zhangsan"

    assert "password_hash" not in body


# ============================================
# 10. 测试 /me 缺少 Token
# ============================================

def test_me_endpoint_without_token_returns_401(api_client):

    response = api_client.get(
        "/api/v1/auth/me"
    )

    assert response.status_code == 401

    assert response.headers["www-authenticate"] == "Bearer"


# ============================================
# 11. 测试不支持 Basic 认证
# ============================================

def test_me_endpoint_rejects_basic_auth(api_client):

    response = api_client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": "Basic dXNlcjpwYXNz"
        },
    )

    assert response.status_code == 401
