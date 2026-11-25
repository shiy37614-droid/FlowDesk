
from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, text
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.user import User

# ============================================
# FlowDesk Role ORM Model
# ============================================

class Role(Base):

    __tablename__ = "roles"

    __table_args__ = (
        UniqueConstraint(
            "code",
            name="uk_roles_code",
        ),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
            "comment": "用户角色表",
        },
    )

    # ========================================
    # 1. 主键
    # ========================================

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
        comment="角色ID",
    )

    # ========================================
    # 2. 角色名称
    # ========================================

    name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="角色名称",
    )

    # ========================================
    # 3. 角色编码
    # ========================================

    code: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="角色编码",
    )

    # ========================================
    # 4. 创建时间
    # ========================================

    created_at: Mapped[datetime] = mapped_column(
        DateTime(),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="创建时间",
    )

    users: Mapped[list["User"]] = relationship(
    back_populates="role",
)