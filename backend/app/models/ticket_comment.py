
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


if TYPE_CHECKING:
    from app.models.ticket import Ticket
    from app.models.user import User


class TicketComment(Base):
    __tablename__ = "ticket_comments"

    __table_args__ = (
        Index(
            "idx_ticket_comments_ticket_created_id",
            "ticket_id",
            "created_at",
            "id",
        ),

        Index(
            "idx_ticket_comments_user_id",
            "user_id",
        ),

        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
            "comment": "工单评论表",
        },
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True).with_variant(
            Integer,
            "sqlite",
        ),
        primary_key=True,
        autoincrement=True,
        comment="评论ID",
    )
    ticket_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey(
            "tickets.id",
            name="fk_ticket_comments_ticket",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
        comment="所属工单ID",
    )

    user_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey(
            "users.id",
            name="fk_ticket_comments_user",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
        comment="评论作者用户ID",
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="评论内容",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="评论创建时间",
    )

    ticket: Mapped["Ticket"] = relationship(
        back_populates="comments",
    )

    user: Mapped["User"] = relationship("User")
