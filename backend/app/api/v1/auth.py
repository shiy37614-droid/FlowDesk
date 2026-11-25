
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import User
from app.schemas.user import UserCreate, UserRead
from app.services.user_service import (
    UsernameAlreadyExistsError,
    DefaultUserRoleNotFoundError,
    create_user,
)

from app.core.security import create_access_token

from app.schemas.user import Token, UserLogin

from app.services.user_service import authenticate_user
from app.api.deps import get_current_user
# ============================================
# FlowDesk Authentication Router
# ============================================

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


# ============================================
# 1. 用户注册
# ============================================

@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="用户注册",
)
def register(
    user_data: UserCreate,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """
    注册普通用户。

    1. 接收并验证注册数据。
    2. 获取数据库 Session。
    3. 调用 user_service 创建用户。
    4. 处理业务异常。
    5. 返回安全的用户信息。
    """

    try:
        new_user = create_user(
            db=db,
            user_data=user_data,
        )

        return new_user

    except UsernameAlreadyExistsError as exc:

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        ) from exc

    except DefaultUserRoleNotFoundError as exc:

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Default USER role is not configured",
        ) from exc


# ============================================
# 2. 用户登录
# ============================================

@router.post(
    "/login",
    response_model=Token,
    summary="用户登录",
)
def login(
    credentials: UserLogin,
    db: Annotated[Session, Depends(get_db)],
) -> Token:

    # 1. 验证用户身份
    user = authenticate_user(
        db=db,
        username=credentials.username,
        password=credentials.password.get_secret_value(),
    )

    # 2. 身份验证失败
    if user is None:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    # 3. 生成 JWT
    access_token = create_access_token(
        subject=user.id
    )

    # 4. 返回 Token
    return Token(
        access_token=access_token,
        token_type="bearer",
    )


# ============================================
# 3. 获取当前登录用户
# ============================================

@router.get(
    "/me",
    response_model=UserRead,
    summary="获取当前登录用户",
)
def read_current_user(
    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],
) -> User:

    return current_user
