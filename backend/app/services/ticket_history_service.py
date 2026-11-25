
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ticket_history import TicketHistory
from app.models.user import User

from app.services.ticket_service import get_ticket


# ============================================
# FlowDesk Ticket History Service
# ============================================


def list_ticket_histories(
    db: Session,
    current_user: User,
    ticket_id: int,
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[TicketHistory], int]:
    """
    查询工单操作历史。

    1. 验证分页参数。
    2. 验证当前用户是否有权访问工单。
    3. 查询该工单的全部历史记录。
    4. 统计历史记录总数。
    5. 按创建时间正序排列。
    6. 使用 ID 保证相同时间下的排序稳定。
    7. 执行分页查询。

    返回：
        历史记录列表、历史记录总数量。
    """

    # ----------------------------------------
    # 1. 检查分页参数
    # ----------------------------------------

    if page < 1 or not 1 <= page_size <= 100:

        raise ValueError(
            "Invalid pagination parameters"
        )

    # ----------------------------------------
    # 2. 验证工单访问权限
    # ----------------------------------------

    ticket = get_ticket(
        db=db,
        current_user=current_user,
        ticket_id=ticket_id,
    )

    # ----------------------------------------
    # 3. 构建历史记录查询条件
    # ----------------------------------------

    conditions = [
        TicketHistory.ticket_id == ticket.id
    ]

    # ----------------------------------------
    # 4. 统计历史记录数量
    # ----------------------------------------

    total = db.scalar(
        select(
            func.count(TicketHistory.id)
        ).where(
            *conditions
        )
    ) or 0

    # ----------------------------------------
    # 5. 分页查询历史记录
    # ----------------------------------------

    statement = (
        select(TicketHistory)
        .where(*conditions)
        .order_by(
            TicketHistory.created_at.asc(),
            TicketHistory.id.asc(),
        )
        .offset(
            (page - 1) * page_size
        )
        .limit(page_size)
    )

    histories = db.scalars(
        statement
    ).all()

    # ----------------------------------------
    # 6. 返回结果
    # ----------------------------------------

    return list(histories), int(total)
