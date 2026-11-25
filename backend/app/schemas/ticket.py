
from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


# ============================================
# 1. 工单创建请求 Schema
# ============================================

class TicketCreate(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
    )

    title: str = Field(
        min_length=1,
        max_length=200,
    )

    description: str = Field(
        min_length=1,
    )

    priority: Literal[
        "LOW",
        "NORMAL",
        "HIGH",
    ] = "NORMAL"

    category_id: int = Field(
        strict=True,
        gt=0,
        le=18446744073709551615,
    )

    # ----------------------------------------
    # 标题和描述：去除首尾空格
    # ----------------------------------------

    @field_validator(
        "title",
        "description",
        mode="before",
    )
    @classmethod
    def strip_text(cls, value):

        if isinstance(value, str):
            return value.strip()

        return value

    # ----------------------------------------
    # 优先级：统一转换为大写
    # ----------------------------------------

    @field_validator(
        "priority",
        mode="before",
    )
    @classmethod
    def normalize_priority(cls, value):

        if isinstance(value, str):
            return value.strip().upper()

        return value


# ============================================
# 2. 工单响应 Schema
# ============================================

class TicketRead(BaseModel):

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    ticket_no: str

    title: str
    description: str

    priority: Literal[
        "LOW",
        "NORMAL",
        "HIGH",
    ]

    status: Literal[
        "OPEN",
        "ASSIGNED",
        "IN_PROGRESS",
        "RESOLVED",
        "CLOSED",
    ]

    creator_id: int
    assignee_id: int | None
    category_id: int

    deleted_at: datetime | None

    created_at: datetime
    updated_at: datetime


# ============================================
# 3. 工单查询类型
# ============================================

TicketPriority = Literal[
    "LOW",
    "NORMAL",
    "HIGH",
]

TicketStatus = Literal[
    "OPEN",
    "ASSIGNED",
    "IN_PROGRESS",
    "RESOLVED",
    "CLOSED",
]


# ============================================
# 4. 工单分页响应 Schema
# ============================================

class TicketListResponse(BaseModel):

    items: list[TicketRead]

    total: int

    page: int

    page_size: int

    total_pages: int



# ============================================
# 5. 工单修改请求 Schema
# ============================================

class TicketUpdate(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
    )

    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )

    description: str | None = Field(
        default=None,
        min_length=1,
    )

    priority: TicketPriority | None = None

    category_id: int | None = Field(
        default=None,
        strict=True,
        gt=0,
        le=18446744073709551615,
    )

    # ----------------------------------------
    # 文本字段去除首尾空格
    # ----------------------------------------

    @field_validator(
        "title",
        "description",
        mode="before",
    )
    @classmethod
    def strip_text(cls, value):

        if isinstance(value, str):
            return value.strip()

        return value

    # ----------------------------------------
    # 优先级统一大写
    # ----------------------------------------

    @field_validator(
        "priority",
        mode="before",
    )
    @classmethod
    def normalize_priority(cls, value):

        if isinstance(value, str):
            return value.strip().upper()

        return value

    # ----------------------------------------
    # PATCH 数据完整性检查
    # ----------------------------------------

    @model_validator(mode="after")
    def validate_patch(self):

        # 不允许空请求
        if not self.model_fields_set:
            raise ValueError(
                "At least one field must be provided"
            )

        # 不允许显式提交 null
        for field_name in self.model_fields_set:

            if getattr(self, field_name) is None:

                raise ValueError(
                    f"{field_name} cannot be null"
                )

        return self


# ============================================
# 6. 工单负责人分配请求 Schema
# ============================================

class TicketAssign(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
    )

    assignee_id: int = Field(
        strict=True,
        gt=0,
        le=18446744073709551615,
    )


# ============================================
# 7. 工单状态修改请求 Schema
# ============================================

class TicketStatusUpdate(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
    )

    status: TicketStatus

    # ----------------------------------------
    # 状态统一转换为大写
    # ----------------------------------------

    @field_validator(
        "status",
        mode="before",
    )
    @classmethod
    def normalize_status(cls, value):

        if isinstance(value, str):
            return value.strip().upper()

        return value
