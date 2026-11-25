
from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


# ============================================
# MySQL BIGINT UNSIGNED 最大值
# ============================================

MYSQL_UNSIGNED_BIGINT_MAX = (
    18446744073709551615
)


# ============================================
# 1. 附件响应 Schema
# ============================================

class TicketAttachmentRead(BaseModel):

    # 允许从 SQLAlchemy ORM 对象读取属性
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int = Field(
        gt=0,
        le=MYSQL_UNSIGNED_BIGINT_MAX,
    )

    ticket_id: int = Field(
        gt=0,
        le=MYSQL_UNSIGNED_BIGINT_MAX,
    )

    uploader_id: int = Field(
        gt=0,
        le=MYSQL_UNSIGNED_BIGINT_MAX,
    )

    original_filename: str = Field(
        min_length=1,
        max_length=255,
    )

    content_type: str = Field(
        min_length=1,
        max_length=100,
    )

    file_size: int = Field(
        gt=0,
        le=MYSQL_UNSIGNED_BIGINT_MAX,
    )

    created_at: datetime


# ============================================
# 2. 附件分页响应 Schema
# ============================================

class TicketAttachmentListResponse(BaseModel):

    items: list[TicketAttachmentRead]

    total: int = Field(
        ge=0,
    )

    page: int = Field(
        ge=1,
    )

    page_size: int = Field(
        ge=1,
        le=100,
    )

    total_pages: int = Field(
        ge=0,
    )
