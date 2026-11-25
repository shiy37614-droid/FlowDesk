
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.user import UserCreate, UserRead


# ============================================
# 1. 测试用户名和昵称规范化
# ============================================

def test_user_create_normalizes_input():

    user = UserCreate(
        username=" ZhangSan ",
        password="123456",
        display_name=" 张三 ",
    )

    assert user.username == "zhangsan"
    assert user.display_name == "张三"
    assert user.password.get_secret_value() == "123456"


# ============================================
# 2. 测试非法用户名
# ============================================

@pytest.mark.parametrize(
    "username",
    [
        "ab",
        "a" * 51,
        "zhang-san",
        "张三",
    ],
)
def test_user_create_rejects_invalid_username(username):

    with pytest.raises(ValidationError):

        UserCreate(
            username=username,
            password="123456",
            display_name="张三",
        )


# ============================================
# 3. 测试不允许客户端指定角色
# ============================================

@pytest.mark.parametrize(
    "extra",
    [
        {"role_id": 1},
        {"role": "ADMIN"},
    ],
)
def test_user_create_rejects_role_fields(extra):

    data = {
        "username": "zhangsan",
        "password": "123456",
        "display_name": "张三",
    }

    data.update(extra)

    with pytest.raises(ValidationError):
        UserCreate(**data)


# ============================================
# 4. 测试空昵称
# ============================================

def test_user_create_rejects_empty_display_name():

    with pytest.raises(ValidationError):

        UserCreate(
            username="zhangsan",
            password="123456",
            display_name="   ",
        )


# ============================================
# 5. 测试 ORM 对象转换
# ============================================

def test_user_read_from_attributes():

    now = datetime(
        2026, 11, 23,
        tzinfo=timezone.utc,
    )

    orm_user = SimpleNamespace(
        id=1,
        username="zhangsan",
        display_name="张三",
        role_id=3,
        created_at=now,
        updated_at=now,
        password_hash="secret_hash",
    )

    result = UserRead.model_validate(orm_user)

    assert result.id == 1
    assert result.username == "zhangsan"
    assert result.display_name == "张三"
    assert result.role_id == 3

    # 响应中绝不能出现密码哈希
    assert "password_hash" not in result.model_dump()
