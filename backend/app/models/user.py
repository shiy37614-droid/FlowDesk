
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from typing import TYPE_CHECKING
from app.models.ticket_attachment import TicketAttachment
if TYPE_CHECKING:
    from app.models.role import Role

# ============================================
# FlowDesk User ORM Model
# ============================================

class User(Base):

    __tablename__ = "users"

    __table_args__ = (
        UniqueConstraint(
            "username",
            name="uk_users_username",
        ),

        Index(
            "idx_users_role_id",
            "role_id",
        ),

        {
            "comment": "用户信息表",
        },
    )

    # ========================================
    # 1. Primary Key
    # ========================================

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
        comment="用户ID",
    )

    # ========================================
    # 2. Basic Information
    # ========================================

    username: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="登录账号",
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="密码哈希",
    )

    display_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="用户昵称",
    )

    # ========================================
    # 3. Foreign Key
    # ========================================

    role_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),

        ForeignKey(
            "roles.id",
            name="fk_users_role",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),

        nullable=False,
        comment="角色ID",
    )

    # ========================================
    # 4. Timestamps
    # ========================================

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="创建时间",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text(
            "CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
        ),
        comment="更新时间",
    )

    # ========================================
    # 5. ORM Relationship
    # ========================================

    role: Mapped["Role"] = relationship(
        back_populates="users",
    )

    uploaded_attachments: Mapped[list["TicketAttachment"]] = relationship(
        back_populates="uploader",
        order_by="TicketAttachment.created_at, TicketAttachment.id",
    )