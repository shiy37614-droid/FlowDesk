
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.ticket_attachment import TicketAttachment

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.ticket_comment import TicketComment
    from app.models.ticket_history import TicketHistory
    from app.models.user import User


class Ticket(Base):
    __tablename__ = "tickets"

    __table_args__ = (
        UniqueConstraint(
            "ticket_no",
            name="uk_tickets_ticket_no",
        ),

        Index(
            "idx_tickets_creator_deleted_created",
            "creator_id",
            "deleted_at",
            "created_at",
        ),

        Index(
            "idx_tickets_assignee_deleted_status_created",
            "assignee_id",
            "deleted_at",
            "status",
            "created_at",
        ),

        Index(
            "idx_tickets_category_id",
            "category_id",
        ),

        Index(
            "idx_tickets_deleted_status_created",
            "deleted_at",
            "status",
            "created_at",
        ),

        CheckConstraint(
            "status IN ('OPEN', 'ASSIGNED', "
            "'IN_PROGRESS', 'RESOLVED', 'CLOSED')",
            name="chk_tickets_status",
        ),

        CheckConstraint(
            "priority IN ('LOW', 'NORMAL', 'HIGH')",
            name="chk_tickets_priority",
        ),

        CheckConstraint(
            "(status = 'OPEN' AND assignee_id IS NULL) "
            "OR (status <> 'OPEN' AND assignee_id IS NOT NULL)",
            name="chk_tickets_assignee",
        ),

        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
            "comment": "工单主表",
        },
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
        comment="工单ID",
    )

    ticket_no: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="工单编号",
    )

    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="工单标题",
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="工单描述",
    )

    priority: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'NORMAL'"),
        comment="优先级",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'OPEN'"),
        comment="工单状态",
    )

    creator_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey(
            "users.id",
            name="fk_tickets_creator",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
        comment="创建人用户ID",
    )

    assignee_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey(
            "users.id",
            name="fk_tickets_assignee",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=True,
        comment="负责人用户ID",
    )

    category_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey(
            "categories.id",
            name="fk_tickets_category",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
        comment="工单分类ID",
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="逻辑删除时间",
    )

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
    # ORM relationships
    # ========================================

    creator: Mapped["User"] = relationship(
        "User",
        foreign_keys=[creator_id],
    )

    assignee: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[assignee_id],
    )

    category: Mapped["Category"] = relationship(
        back_populates="tickets",
    )

    comments: Mapped[list["TicketComment"]] = relationship(
        back_populates="ticket",
        order_by="TicketComment.created_at, TicketComment.id",
    )

    histories: Mapped[list["TicketHistory"]] = relationship(
        back_populates="ticket",
        order_by="TicketHistory.created_at, TicketHistory.id",
    )

    attachments: Mapped[list["TicketAttachment"]] = relationship(
        back_populates="ticket",
        order_by="TicketAttachment.created_at, TicketAttachment.id",
    )