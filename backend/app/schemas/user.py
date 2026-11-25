
from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
)
from typing import Literal

# ============================================
# 1. 用户注册请求 Schema
# ============================================

class UserCreate(BaseModel):

    # 不允许客户端提交未声明的字段
    model_config = ConfigDict(extra="forbid")

    username: str = Field(
        min_length=3,
        max_length=50,
        pattern=r"^[a-z0-9_]+$",
    )

    password: SecretStr = Field(
        min_length=1,
    )

    display_name: str = Field(
        min_length=1,
        max_length=100,
    )

    # 用户名：去除空格，统一转换为小写
    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value):
        if isinstance(value, str):
            return value.strip().lower()

        return value

    # 昵称：去除首尾空格
    @field_validator("display_name", mode="before")
    @classmethod
    def strip_display_name(cls, value):
        if isinstance(value, str):
            return value.strip()

        return value


# ============================================
# 2. 用户响应 Schema
# ============================================

class UserRead(BaseModel):

    # 允许从 SQLAlchemy ORM 对象读取属性
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    role_id: int

    created_at: datetime
    updated_at: datetime



# ============================================
# 3. 用户登录请求 Schema
# ============================================

class UserLogin(BaseModel):

    model_config = ConfigDict(extra="forbid")

    username: str = Field(
        min_length=3,
        max_length=50,
        pattern=r"^[a-z0-9_]+$",
    )

    password: SecretStr = Field(
        min_length=1,
    )

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value):
        if isinstance(value, str):
            return value.strip().lower()

        return value


# ============================================
# 4. JWT Token 响应 Schema
# ============================================

class Token(BaseModel):

    access_token: str

    token_type: Literal["bearer"] = "bearer"