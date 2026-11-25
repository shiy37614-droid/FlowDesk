
from uuid import uuid4

import pytest

from sqlalchemy import delete, select

from app.core.security import verify_password
from app.db.session import SessionLocal
from app.models import Role, User
from app.schemas.user import UserCreate
from app.services.user_service import (
    create_user,
    UsernameAlreadyExistsError,
)


def test_create_user_success():

    username = f"test_{uuid4().hex[:12]}"

    with SessionLocal() as db:

        try:
            user_data = UserCreate(
                username=username,
                password="TestPass123!",
                display_name="测试用户",
            )

            user = create_user(db, user_data)

            user_role = db.scalar(
                select(Role).where(
                    Role.code == "USER"
                )
            )

            assert user.id is not None
            assert user.username == username
            assert user.display_name == "测试用户"

            assert user.role_id == user_role.id

            assert user.password_hash.startswith(
                "$argon2id$"
            )

            assert verify_password(
                "TestPass123!",
                user.password_hash,
            )

            assert not verify_password(
                "WrongPassword",
                user.password_hash,
            )

        finally:
            db.rollback()

            db.execute(
                delete(User).where(
                    User.username == username
                )
            )

            db.commit()


def test_create_user_rejects_duplicate_username():

    username = f"test_{uuid4().hex[:12]}"

    with SessionLocal() as db:

        try:
            user_data = UserCreate(
                username=username,
                password="TestPass123!",
                display_name="测试用户",
            )

            create_user(db, user_data)

            with pytest.raises(
                UsernameAlreadyExistsError
            ):
                create_user(db, user_data)

        finally:
            db.rollback()

            db.execute(
                delete(User).where(
                    User.username == username
                )
            )

            db.commit()
