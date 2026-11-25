
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import Role, User
from app.schemas.user import UserCreate
from app.core.security import hash_password, verify_password

# ============================================
# 1. 自定义业务异常
# ============================================

class UsernameAlreadyExistsError(Exception):
    """用户名已经存在。"""


class DefaultUserRoleNotFoundError(Exception):
    """数据库中不存在默认 USER 角色。"""


# ============================================
# 2. 创建用户
# ============================================

def create_user(
    db: Session,
    user_data: UserCreate,
) -> User:
    """
    创建普通用户。

    1. 检查用户名是否存在。
    2. 查询默认 USER 角色。
    3. 对密码进行 Argon2id 哈希。
    4. 创建用户并提交事务。
    5. 返回创建后的 ORM 对象。
    """

    username = user_data.username

    # ----------------------------------------
    # 检查用户名是否已经存在
    # ----------------------------------------

    existing_user = db.scalar(
        select(User.id).where(
            User.username == username
        )
    )

    if existing_user is not None:
        raise UsernameAlreadyExistsError(
            "Username already exists"
        )

    # ----------------------------------------
    # 查询默认 USER 角色
    # ----------------------------------------

    user_role = db.scalar(
        select(Role).where(
            Role.code == "USER"
        )
    )

    if user_role is None:
        raise DefaultUserRoleNotFoundError(
            "Default USER role is not configured"
        )

    # ----------------------------------------
    # 密码哈希
    # ----------------------------------------

    password_hash = hash_password(
        user_data.password.get_secret_value()
    )

    # ----------------------------------------
    # 创建用户对象
    # ----------------------------------------

    new_user = User(
        username=username,
        password_hash=password_hash,
        display_name=user_data.display_name,
        role_id=user_role.id,
    )

    db.add(new_user)

    # ----------------------------------------
    # 提交数据库事务
    # ----------------------------------------

    try:
        db.commit()

    except IntegrityError as exc:

        db.rollback()

        # 处理并发注册导致的唯一索引冲突
        existing_user = db.scalar(
            select(User.id).where(
                User.username == username
            )
        )

        if existing_user is not None:
            raise UsernameAlreadyExistsError(
                "Username already exists"
            ) from exc

        # 其他数据库完整性错误不能伪装成用户名重复
        raise

    # ----------------------------------------
    # 刷新 ORM 对象
    # ----------------------------------------

    db.refresh(new_user)

    return new_user

# ============================================
# 3. 用户身份验证
# ============================================

def authenticate_user(
    db: Session,
    username: str,
    password: str,
) -> User | None:
    """
    验证用户身份。

    1. 根据用户名查询用户。
    2. 检查用户是否存在。
    3. 验证密码。
    4. 返回用户对象或 None。
    """

    user = db.scalar(
        select(User).where(
            User.username == username
        )
    )

    if user is None:
        return None

    if not verify_password(
        password,
        user.password_hash,
    ):
        return None

    return user