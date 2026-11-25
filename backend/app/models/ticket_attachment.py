
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
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


if TYPE_CHECKING:
    from app.models.ticket import Ticket
    from app.models.user import User


class TicketAttachment(Base):

    __tablename__ = "ticket_attachments"

    __table_args__ = (
        # 存储标识必须唯一
        UniqueConstraint(
            "storage_key",
            name="uk_ticket_attachments_storage_key",
        ),

        # 工单附件查询索引
        Index(
            "idx_ticket_attachments_ticket_deleted_created_id",
            "ticket_id",
            "deleted_at",
            "created_at",
            "id",
        ),

        # 上传用户查询索引
        Index(
            "idx_ticket_attachments_uploader_id",
            "uploader_id",
        ),

        # 文件大小必须大于 0
        CheckConstraint(
            "file_size > 0",
            name="chk_ticket_attachments_file_size",
        ),

        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
            "comment": "工单附件表",
        },
    )

    # ========================================
    # 1. Primary Key
    # ========================================

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
        comment="附件ID",
    )

    # ========================================
    # 2. Foreign Keys
    # ========================================

    ticket_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey(
            "tickets.id",
            name="fk_ticket_attachments_ticket",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
        comment="所属工单ID",
    )

    uploader_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey(
            "users.id",
            name="fk_ticket_attachments_uploader",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
        comment="上传用户ID",
    )

    # ========================================
    # 3. File Information
    # ========================================

    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="原始文件名",
    )

    storage_key: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="服务器内部文件存储标识",
    )

    content_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="文件MIME类型",
    )

    file_size: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        nullable=False,
        comment="文件大小（字节）",
    )

    # ========================================
    # 4. Timestamps
    # ========================================

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="上传时间",
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="逻辑删除时间",
    )

    # ========================================
    # 5. ORM Relationships
    # ========================================

    ticket: Mapped["Ticket"] = relationship(
        back_populates="attachments",
    )

    uploader: Mapped["User"] = relationship(
        back_populates="uploaded_attachments",
    )
