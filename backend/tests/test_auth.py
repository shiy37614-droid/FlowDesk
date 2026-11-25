
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import get_db
from app.api.v1 import auth as auth_module

from app.services.user_service import (
    UsernameAlreadyExistsError,
    DefaultUserRoleNotFoundError,
)


# ============================================
# 1. 测试客户端
# ============================================

@pytest.fixture
def client():

    old_overrides = app.dependency_overrides.copy()

    def override_get_db():
        yield object()

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client

    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(old_overrides)


# ============================================
# 2. 模拟用户对象
# ============================================

def fake_user(username="zhangsan"):

    now = datetime(2026, 11, 23, 20, 0, 0)

    return SimpleNamespace(
        id=10,
        username=username,
        display_name="张三",
        role_id=6,
        created_at=now,
        updated_at=now,
        password_hash="must-not-leak",
    )


# ============================================
# 3. 测试注册成功
# ============================================

def test_register_success_returns_201_and_safe_user_fields(
    client,
    monkeypatch,
):

    called = {}

    def fake_create_user(db, user_data):

        called["data"] = user_data

        return fake_user(username=user_data.username)

    monkeypatch.setattr(
        auth_module,
        "create_user",
        fake_create_user,
    )

    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": " ZhangSan ",
            "password": "123456",
            "display_name": " 张三 ",
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["username"] == "zhangsan"
    assert body["display_name"] == "张三"
    assert body["role_id"] == 6

    assert "password" not in body
    assert "password_hash" not in body

    assert called["data"].username == "zhangsan"


# ============================================
# 4. 测试用户名重复
# ============================================

def test_register_duplicate_username_returns_409(
    client,
    monkeypatch,
):

    def fake_create_user(db, user_data):

        raise UsernameAlreadyExistsError()

    monkeypatch.setattr(
        auth_module,
        "create_user",
        fake_create_user,
    )

    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "zhangsan",
            "password": "123456",
            "display_name": "张三",
        },
    )

    assert response.status_code == 409

    assert response.json()["detail"] == (
        "Username already exists"
    )


# ============================================
# 5. 测试默认角色不存在
# ============================================

def test_register_missing_default_role_returns_500(
    client,
    monkeypatch,
):

    def fake_create_user(db, user_data):

        raise DefaultUserRoleNotFoundError()

    monkeypatch.setattr(
        auth_module,
        "create_user",
        fake_create_user,
    )

    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "zhangsan",
            "password": "123456",
            "display_name": "张三",
        },
    )

    assert response.status_code == 500


# ============================================
# 6. 测试非法注册数据
# ============================================

@pytest.mark.parametrize(
    "payload",
    [
        {
            "username": "ab",
            "password": "123456",
            "display_name": "张三",
        },
        {
            "username": "Bad Name",
            "password": "123456",
            "display_name": "张三",
        },
        {
            "username": "zhangsan",
            "password": "123456",
            "display_name": "   ",
        },
        {
            "username": "zhangsan",
            "password": "123456",
            "display_name": "张三",
            "role_id": 4,
        },
        {
            "username": "zhangsan",
            "password": "",
            "display_name": "张三",
        },
    ],
)
def test_register_invalid_payload_returns_422(
    client,
    monkeypatch,
    payload,
):

    def should_not_run(*args):
        raise AssertionError(
            "Service should not run for invalid payload"
        )

    monkeypatch.setattr(
        auth_module,
        "create_user",
        should_not_run,
    )

    response = client.post(
        "/api/v1/auth/register",
        json=payload,
    )

    assert response.status_code == 422


# ============================================
# 7. 测试 OpenAPI 路由注册
# ============================================

def test_register_route_is_in_openapi(client):

    schema = client.get(
        "/openapi.json"
    ).json()

    assert "/api/v1/auth/register" in schema["paths"]


# ============================================
# 8. 登录成功
# ============================================

def test_login_success(client, monkeypatch):

    called = {}

    def fake_authenticate_user(db, username, password):

        called["username"] = username
        called["password"] = password

        return fake_user(username=username)

    def fake_create_access_token(subject):

        assert subject == 10

        return "test-access-token"

    monkeypatch.setattr(
        auth_module,
        "authenticate_user",
        fake_authenticate_user,
    )

    monkeypatch.setattr(
        auth_module,
        "create_access_token",
        fake_create_access_token,
    )

    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": "zhangsan",
            "password": "123456",
        },
    )

    assert response.status_code == 200

    assert response.json() == {
        "access_token": "test-access-token",
        "token_type": "bearer",
    }

    assert called["username"] == "zhangsan"
    assert called["password"] == "123456"


# ============================================
# 9. 登录失败
# ============================================

def test_login_invalid_credentials(client, monkeypatch):

    def fake_authenticate_user(db, username, password):
        return None

    monkeypatch.setattr(
        auth_module,
        "authenticate_user",
        fake_authenticate_user,
    )

    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": "zhangsan",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401

    assert response.json()["detail"] == (
        "Incorrect username or password"
    )

    assert response.headers["www-authenticate"] == "Bearer"


# ============================================
# 10. 登录数据验证失败
# ============================================

def test_login_invalid_payload(client, monkeypatch):

    def should_not_run(*args, **kwargs):
        raise AssertionError(
            "Service should not run"
        )

    monkeypatch.setattr(
        auth_module,
        "authenticate_user",
        should_not_run,
    )

    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": "ab",
            "password": "",
        },
    )

    assert response.status_code == 422