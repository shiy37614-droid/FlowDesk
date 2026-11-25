
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User


# ============================================
# 1. 角色编码
# ============================================

VALID_ROLE_CODES = frozenset({
    "ADMIN",
    "AGENT",
    "USER",
})


# ============================================
# 2. HTTP Bearer Token 提取器
# ============================================

bearer_scheme = HTTPBearer(
    auto_error=False,
)


# ============================================
# 3. 统一身份认证异常
# ============================================

def _unauthorized() -> HTTPException:

    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={
            "WWW-Authenticate": "Bearer"
        },
    )


# ============================================
# 4. 获取当前登录用户
# ============================================

def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> User:

    # 检查 Token
    if credentials is None:
        raise _unauthorized()

    # 验证 JWT
    payload = decode_access_token(
        credentials.credentials
    )

    if payload is None:
        raise _unauthorized()

    # 获取用户 ID
    subject = payload.get("sub")

    if (
        not isinstance(subject, str)
        or not (subject.isascii() and subject.isdigit())
    ):
        raise _unauthorized()

    user_id = int(subject)

    if user_id <= 0:
        raise _unauthorized()

    # 查询数据库
    user = db.get(
        User,
        user_id,
    )

    if user is None:
        raise _unauthorized()

    return user


# ============================================
# 5. 角色权限检查
# ============================================

def require_roles(*allowed_roles: str):
    """
    创建角色权限检查依赖。

    参数：
        allowed_roles：允许访问的角色编码。

    返回：
        有权限的当前用户。

    权限不足：
        HTTP 403。
    """

    # 检查角色配置
    if not allowed_roles or any(
        not isinstance(role, str) or not role.strip()
        for role in allowed_roles
    ):
        raise ValueError(
            "At least one valid role code is required"
        )

    normalized_roles = {
        role.strip().upper()
        for role in allowed_roles
    }

    unknown_roles = normalized_roles - VALID_ROLE_CODES

    if unknown_roles:
        raise ValueError(
            f"Unknown role codes: {sorted(unknown_roles)}"
        )

    # 内部权限检查函数
    def role_checker(
        current_user: Annotated[
            User,
            Depends(get_current_user),
        ],
    ) -> User:

        # 获取用户角色编码
        user_role = current_user.role.code

        # 判断是否有权限
        if user_role not in normalized_roles:

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        return current_user

    return role_checker
