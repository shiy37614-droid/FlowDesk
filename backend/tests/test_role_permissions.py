
from types import SimpleNamespace
from typing import Annotated

import pytest

from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.deps import (
    get_current_user,
    require_roles,
)
from app.models import User


# ============================================
# 1. 创建模拟用户
# ============================================

def make_user(role_code):

    return SimpleNamespace(
        id=5,
        role=SimpleNamespace(
            code=role_code,
        ),
    )


# ============================================
# 2. ADMIN 允许访问
# ============================================

def test_admin_role_allowed():

    user = make_user("ADMIN")

    checker = require_roles("ADMIN")

    assert checker(user) is user


# ============================================
# 3. USER 不允许访问管理员接口
# ============================================

def test_user_role_forbidden():

    user = make_user("USER")

    checker = require_roles("ADMIN")

    with pytest.raises(HTTPException) as exc:

        checker(user)

    assert exc.value.status_code == 403


# ============================================
# 4. 多角色允许访问
# ============================================

def test_multiple_roles_allowed():

    user = make_user("AGENT")

    checker = require_roles(
        "ADMIN",
        "AGENT",
    )

    assert checker(user) is user


# ============================================
# 5. 角色编码忽略大小写和首尾空格
# ============================================

def test_role_code_normalization():

    user = make_user("ADMIN")

    checker = require_roles(" admin ")

    assert checker(user) is user


# ============================================
# 6. 不允许空角色配置
# ============================================

def test_empty_roles_rejected():

    with pytest.raises(ValueError):

        require_roles()


# ============================================
# 7. 不允许未知角色
# ============================================

def test_unknown_role_rejected():

    with pytest.raises(ValueError):

        require_roles("ROOT")


# ============================================
# 8. FastAPI 依赖注入测试
# ============================================

@pytest.fixture
def test_app():

    app = FastAPI()

    @app.get("/admin")
    def admin_route(
        current_user: Annotated[
            User,
            Depends(require_roles("ADMIN")),
        ],
    ):

        return {
            "user_id": current_user.id
        }

    yield app

    app.dependency_overrides.clear()


# ============================================
# 9. 管理员访问接口成功
# ============================================

def test_admin_endpoint_success(test_app):

    test_app.dependency_overrides[
        get_current_user
    ] = lambda: make_user("ADMIN")

    client = TestClient(test_app)

    response = client.get("/admin")

    assert response.status_code == 200

    assert response.json() == {
        "user_id": 5
    }


# ============================================
# 10. 普通用户访问管理员接口失败
# ============================================

def test_user_endpoint_forbidden(test_app):

    test_app.dependency_overrides[
        get_current_user
    ] = lambda: make_user("USER")

    client = TestClient(test_app)

    response = client.get("/admin")

    assert response.status_code == 403

    assert response.json()["detail"] == (
        "Insufficient permissions"
    )
