
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


# ============================================
# 1. 工单历史记录响应 Schema
# ============================================

class TicketHistoryRead(BaseModel):

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    ticket_id: int

    operator_id: int

    action_type: str

    field_name: str

    old_value: Any | None = None

    new_value: Any | None = None

    created_at: datetime


# ============================================
# 2. 工单历史分页响应 Schema
# ============================================

class TicketHistoryListResponse(BaseModel):

    items: list[TicketHistoryRead]

    total: int

    page: int

    page_size: int

    total_pages: int
