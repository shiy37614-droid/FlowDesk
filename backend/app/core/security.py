
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from jwt import InvalidTokenError

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import settings


# ============================================
# 1. 密码哈希器
# ============================================

password_hasher = PasswordHasher()


# ============================================
# 2. JWT 配置
# ============================================

JWT_ALGORITHM = "HS256"


# ============================================
# 3. 密码哈希
# ============================================

def hash_password(password: str) -> str:

    if not isinstance(password, str):
        raise TypeError("password must be a string")

    if password == "":
        raise ValueError("password must not be empty")

    return password_hasher.hash(password)


# ============================================
# 4. 验证密码
# ============================================

def verify_password(
    password: str,
    password_hash: str,
) -> bool:

    if not isinstance(password, str):
        return False

    if not isinstance(password_hash, str):
        return False

    try:
        return password_hasher.verify(
            password_hash,
            password,
        )

    except (VerificationError, InvalidHashError):
        return False


# ============================================
# 5. 创建 JWT Access Token
# ============================================

def create_access_token(
    subject: str | int,
) -> str:

    subject_value = str(subject)

    if not subject_value:
        raise ValueError("subject must not be empty")

    # 获取当前 UTC 时间
    now = datetime.now(timezone.utc)

    # 计算过期时间
    expires_at = now + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )

    # JWT Payload
    payload = {
        "sub": subject_value,
        "iat": now,
        "exp": expires_at,
    }

    # 生成 Token
    token = jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=JWT_ALGORITHM,
    )

    return token


# ============================================
# 6. 验证并解析 JWT Access Token
# ============================================

def decode_access_token(
    token: str,
) -> dict[str, Any] | None:

    if not isinstance(token, str) or not token:
        return None

    try:

        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[JWT_ALGORITHM],
            options={
                "require": ["sub", "exp"],
            },
        )

    except InvalidTokenError:

        return None

    # 确保用户身份字段有效
    if not isinstance(payload.get("sub"), str):
        return None

    if not payload["sub"]:
        return None

    return payload
