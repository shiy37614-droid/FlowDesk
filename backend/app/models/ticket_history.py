
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    text,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


if TYPE_CHECKING:
    from app.models.ticket import Ticket
    from app.models.user import User


class TicketHistory(Base):
    __tablename__ = "ticket_histories"

    __table_args__ = (
        Index(
            "idx_ticket_histories_ticket_created_id",
            "ticket_id",
            "created_at",
            "id",
        ),

        Index(
            "idx_ticket_histories_operator_id",
            "operator_id",
        ),

        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
            "comment": "工单操作历史表",
        },
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True).with_variant(
            Integer,
            "sqlite",
        ),
        primary_key=True,
        autoincrement=True,
        comment="历史记录ID",
    )
    ticket_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey(
            "tickets.id",
            name="fk_ticket_histories_ticket",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
        comment="所属工单ID",
    )

    operator_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey(
            "users.id",
            name="fk_ticket_histories_operator",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
        comment="操作人用户ID",
    )

    action_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="操作类型",
    )

    field_name: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="变更字段",
    )

    old_value: Mapped[Any | None] = mapped_column(
        JSON(none_as_null=True),
        nullable=True,
        comment="变更前的值",
    )

    new_value: Mapped[Any | None] = mapped_column(
        JSON(none_as_null=True),
        nullable=True,
        comment="变更后的值",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="操作记录时间",
    )

    ticket: Mapped["Ticket"] = relationship(
        back_populates="histories",
    )

    operator: Mapped["User"] = relationship("User")
