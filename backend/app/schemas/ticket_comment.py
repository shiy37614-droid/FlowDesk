
from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


# ============================================
# 1. 创建评论请求 Schema
# ============================================

class TicketCommentCreate(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
    )

    content: str = Field(
        min_length=1,
        max_length=5000,
    )

    @field_validator(
        "content",
        mode="before",
    )
    @classmethod
    def strip_content(cls, value):

        if isinstance(value, str):
            return value.strip()

        return value


# ============================================
# 2. 评论响应 Schema
# ============================================

class TicketCommentRead(BaseModel):

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    ticket_id: int
    user_id: int
    content: str
    created_at: datetime


# ============================================
# 3. 评论分页响应 Schema
# ============================================

class TicketCommentListResponse(BaseModel):

    items: list[TicketCommentRead]

    total: int

    page: int

    page_size: int

    total_pages: int
