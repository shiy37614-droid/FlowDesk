
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,
    Query,
    status,
)

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db

from app.models.user import User
from app.models.ticket import Ticket

from app.schemas.ticket import (
    TicketCreate,
    TicketRead,
    TicketListResponse,
    TicketPriority,
    TicketStatus,
    TicketUpdate,
    TicketAssign,
)

from app.services.ticket_service import (
    CategoryNotFoundError,
    TicketNumberLockTimeoutError,
    TicketNumberExhaustedError,
    TicketNumberGenerationError,
    UnsupportedTicketRoleError,
    TicketNotFoundError,
    TicketAssignmentForbiddenError,
    AssigneeNotFoundError,
    AssigneeNotAgentError,
    TicketNotAssignableError,
    create_ticket,
    list_tickets as query_tickets,
    get_ticket as query_ticket,
    update_ticket as modify_ticket,
    assign_ticket as assign_ticket_service,
)

from app.schemas.ticket import TicketStatusUpdate

from app.services.ticket_service import (
    transition_ticket_status as change_ticket_status,
    TicketStatusTransitionForbiddenError,
    TicketStatusTransitionNotAllowedError,
)

from app.schemas.ticket_comment import (
    TicketCommentCreate,
    TicketCommentRead,
    TicketCommentListResponse,
)

from app.services.ticket_service import (
    create_ticket_comment,
    list_ticket_comments as query_ticket_comments,
    TicketClosedForCommentError,
    create_ticket_comment,
    list_ticket_comments as query_ticket_comments,
    TicketClosedForCommentError,
)
from app.schemas.ticket_comment import (
    TicketCommentCreate,
    TicketCommentRead,
    TicketCommentListResponse,
)

from app.schemas.ticket_history import (
    TicketHistoryListResponse,
)
from app.services.ticket_history_service import (
    list_ticket_histories as query_ticket_histories,
)
# ============================================
# FlowDesk Ticket Router
# ============================================

router = APIRouter(
    prefix="/tickets",
    tags=["Tickets"],
)


# ============================================
# 1. 创建工单
# ============================================

@router.post(
    "",
    response_model=TicketRead,
    status_code=status.HTTP_201_CREATED,
    summary="创建工单",
)
def create_ticket_endpoint(
    ticket_data: TicketCreate,

    db: Annotated[
        Session,
        Depends(get_db),
    ],

    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],
) -> Ticket:

    """
    创建工单接口。

    1. 验证请求数据。
    2. 获取当前登录用户。
    3. 调用工单 Service。
    4. 处理业务异常。
    5. 返回工单信息。
    """

    try:

        return create_ticket(
            db=db,
            ticket_data=ticket_data,
            current_user=current_user,
        )

    except CategoryNotFoundError as exc:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        ) from exc

    except TicketNumberLockTimeoutError as exc:

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ticket number generation is busy; please retry",
            headers={
                "Retry-After": "1",
            },
        ) from exc

    except TicketNumberExhaustedError as exc:

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Daily ticket number capacity reached",
        ) from exc

    except TicketNumberGenerationError as exc:

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ticket number generation failed",
        ) from exc

    except SQLAlchemyError as exc:

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operation failed",
        ) from exc




# ============================================
# 2. 查询工单列表
# ============================================

@router.get(
    "",
    response_model=TicketListResponse,
    summary="查询工单列表",
)
def list_tickets_endpoint(

    db: Annotated[
        Session,
        Depends(get_db),
    ],

    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],

    # 分页参数
    page: Annotated[
        int,
        Query(ge=1),
    ] = 1,

    page_size: Annotated[
        int,
        Query(ge=1, le=100),
    ] = 20,

    # 状态筛选
    status_filter: Annotated[
        TicketStatus | None,
        Query(alias="status"),
    ] = None,

    # 优先级筛选
    priority: Annotated[
        TicketPriority | None,
        Query(),
    ] = None,

    # 分类筛选
    category_id: Annotated[
        int | None,
        Query(gt=0),
    ] = None,

) -> TicketListResponse:

    """
    查询当前用户有权限查看的工单列表。
    """

    try:

        tickets, total = query_tickets(
            db=db,
            current_user=current_user,
            page=page,
            page_size=page_size,
            status=status_filter,
            priority=priority,
            category_id=category_id,
        )

    except UnsupportedTicketRoleError as exc:

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unsupported role for ticket listing",
        ) from exc

    except SQLAlchemyError as exc:

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operation failed",
        ) from exc

    # 计算总页数
    total_pages = (
        total + page_size - 1
    ) // page_size

    return TicketListResponse(
        items=tickets,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )



# ============================================
# 3. 查询工单详情
# ============================================

@router.get(
    "/{ticket_id}",
    response_model=TicketRead,
    summary="查询工单详情",
)
def get_ticket_endpoint(

    ticket_id: Annotated[
        int,
        Path(gt=0),
    ],

    db: Annotated[
        Session,
        Depends(get_db),
    ],

    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],

) -> Ticket:

    """
    查询指定工单详情。

    1. 验证工单 ID。
    2. 获取当前登录用户。
    3. 调用 Service 查询工单。
    4. 处理权限和业务异常。
    5. 返回工单详情。
    """

    try:

        return query_ticket(
            db=db,
            current_user=current_user,
            ticket_id=ticket_id,
        )

    except TicketNotFoundError as exc:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        ) from exc

    except UnsupportedTicketRoleError as exc:

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unsupported role for ticket access",
        ) from exc

    except SQLAlchemyError as exc:

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operation failed",
        ) from exc



# ============================================
# 4. 修改工单
# ============================================

@router.patch(
    "/{ticket_id}",
    response_model=TicketRead,
    summary="修改工单",
)
def update_ticket_endpoint(

    ticket_id: Annotated[
        int,
        Path(gt=0),
    ],

    ticket_data: TicketUpdate,

    db: Annotated[
        Session,
        Depends(get_db),
    ],

    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],

) -> Ticket:

    """
    修改工单接口。

    1. 验证工单 ID。
    2. 获取当前登录用户。
    3. 调用修改工单 Service。
    4. 处理业务异常。
    5. 返回修改后的工单。
    """

    try:

        return modify_ticket(
            db=db,
            ticket_data=ticket_data,
            current_user=current_user,
            ticket_id=ticket_id,
        )

    except TicketNotFoundError as exc:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        ) from exc

    except CategoryNotFoundError as exc:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        ) from exc

    except UnsupportedTicketRoleError as exc:

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unsupported role for ticket update",
        ) from exc

    except SQLAlchemyError as exc:

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operation failed",
        ) from exc



# ============================================
# 5. 分配工单负责人
# ============================================

@router.patch(
    "/{ticket_id}/assign",
    response_model=TicketRead,
    summary="分配工单负责人",
)
def assign_ticket_endpoint(

    ticket_id: Annotated[
        int,
        Path(gt=0),
    ],

    assignment_data: TicketAssign,

    db: Annotated[
        Session,
        Depends(get_db),
    ],

    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],

) -> Ticket:

    """
    分配工单负责人。

    1. 验证工单 ID。
    2. 获取当前登录用户。
    3. 调用分配工单 Service。
    4. 处理业务异常。
    5. 返回分配后的工单。
    """

    try:

        return assign_ticket_service(
            db=db,
            ticket_id=ticket_id,
            assignee_id=assignment_data.assignee_id,
            current_user=current_user,
        )

    except TicketAssignmentForbiddenError as exc:

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only ADMIN can assign tickets",
        ) from exc

    except TicketNotFoundError as exc:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        ) from exc

    except AssigneeNotFoundError as exc:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignee not found",
        ) from exc

    except AssigneeNotAgentError as exc:

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Assignee must have AGENT role",
        ) from exc

    except TicketNotAssignableError as exc:

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ticket is not available for assignment",
        ) from exc

    except SQLAlchemyError as exc:

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operation failed",
        ) from exc



# ============================================
# 6. 工单状态流转
# ============================================

@router.patch(
    "/{ticket_id}/status",
    response_model=TicketRead,
    summary="修改工单状态",
)
def transition_ticket_status_endpoint(

    ticket_id: Annotated[
        int,
        Path(gt=0),
    ],

    status_data: TicketStatusUpdate,

    db: Annotated[
        Session,
        Depends(get_db),
    ],

    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],

) -> Ticket:

    """
    工单状态流转接口。

    1. 验证工单 ID。
    2. 获取当前登录用户。
    3. 调用状态流转 Service。
    4. 处理业务异常。
    5. 返回修改后的工单。
    """

    try:

        return change_ticket_status(
            db=db,
            ticket_id=ticket_id,
            target_status=status_data.status,
            current_user=current_user,
        )

    except TicketNotFoundError as exc:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        ) from exc

    except TicketStatusTransitionForbiddenError as exc:

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to perform this transition",
        ) from exc

    except TicketStatusTransitionNotAllowedError as exc:

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invalid ticket status transition",
        ) from exc

    except SQLAlchemyError as exc:

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operation failed",
        ) from exc



# ============================================
# 7. 创建工单评论
# ============================================

@router.post(
    "/{ticket_id}/comments",
    response_model=TicketCommentRead,
    status_code=status.HTTP_201_CREATED,
    summary="创建工单评论",
)
def create_ticket_comment_endpoint(

    ticket_id: Annotated[
        int,
        Path(gt=0),
    ],

    comment_data: TicketCommentCreate,

    db: Annotated[
        Session,
        Depends(get_db),
    ],

    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],

) -> TicketCommentRead:

    try:

        return create_ticket_comment(
            db=db,
            ticket_id=ticket_id,
            comment_data=comment_data,
            current_user=current_user,
        )

    except TicketNotFoundError as exc:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        ) from exc

    except UnsupportedTicketRoleError as exc:

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unsupported role for commenting",
        ) from exc

    except TicketClosedForCommentError as exc:

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Closed ticket does not accept new comments",
        ) from exc

    except SQLAlchemyError as exc:

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operation failed",
        ) from exc


# ============================================
# 8. 查询工单评论
# ============================================

@router.get(
    "/{ticket_id}/comments",
    response_model=TicketCommentListResponse,
    summary="查询工单评论",
)
def list_ticket_comments_endpoint(

    ticket_id: Annotated[
        int,
        Path(gt=0),
    ],

    db: Annotated[
        Session,
        Depends(get_db),
    ],

    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],

    page: Annotated[
        int,
        Query(ge=1),
    ] = 1,

    page_size: Annotated[
        int,
        Query(ge=1, le=100),
    ] = 20,

) -> TicketCommentListResponse:

    try:

        comments, total = query_ticket_comments(
            db=db,
            current_user=current_user,
            ticket_id=ticket_id,
            page=page,
            page_size=page_size,
        )

    except TicketNotFoundError as exc:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        ) from exc

    except UnsupportedTicketRoleError as exc:

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unsupported role for comment listing",
        ) from exc

    except SQLAlchemyError as exc:

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operation failed",
        ) from exc

    total_pages = (
        total + page_size - 1
    ) // page_size

    return TicketCommentListResponse(
        items=comments,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )




# ============================================
# 9. 查询工单操作历史
# ============================================

@router.get(
    "/{ticket_id}/histories",
    response_model=TicketHistoryListResponse,
    summary="查询工单操作历史",
)
def list_ticket_histories_endpoint(

    ticket_id: Annotated[
        int,
        Path(gt=0),
    ],

    db: Annotated[
        Session,
        Depends(get_db),
    ],

    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],

    # 分页参数
    page: Annotated[
        int,
        Query(ge=1),
    ] = 1,

    page_size: Annotated[
        int,
        Query(ge=1, le=100),
    ] = 20,

) -> TicketHistoryListResponse:

    """
    查询工单操作历史。

    1. 验证工单 ID。
    2. 获取当前登录用户。
    3. 验证工单访问权限。
    4. 调用 History Service。
    5. 执行分页。
    6. 返回历史记录。
    """

    try:

        histories, total = query_ticket_histories(
            db=db,
            current_user=current_user,
            ticket_id=ticket_id,
            page=page,
            page_size=page_size,
        )

    except TicketNotFoundError as exc:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        ) from exc

    except UnsupportedTicketRoleError as exc:

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unsupported role for ticket history access",
        ) from exc

    except SQLAlchemyError as exc:

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operation failed",
        ) from exc

    # ----------------------------------------
    # 计算总页数
    # ----------------------------------------

    total_pages = (
        total + page_size - 1
    ) // page_size

    # ----------------------------------------
    # 返回分页响应
    # ----------------------------------------

    return TicketHistoryListResponse(
        items=histories,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
