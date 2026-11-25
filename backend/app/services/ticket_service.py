
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.ticket import Ticket
from app.models.ticket_comment import TicketComment
from app.models.ticket_history import TicketHistory
from app.models.user import User

from app.schemas.ticket import (
    TicketCreate,
    TicketPriority,
    TicketStatus,
    TicketUpdate,
)

from app.schemas.ticket_comment import TicketCommentCreate

# ============================================
# 1. 自定义业务异常
# ============================================

class CategoryNotFoundError(Exception):
    """工单分类不存在。"""


class TicketNumberLockTimeoutError(Exception):
    """获取工单编号锁超时。"""


class TicketNumberExhaustedError(Exception):
    """当日工单编号已经用完。"""


class TicketNumberGenerationError(Exception):
    """工单编号生成失败。"""

class UnsupportedTicketRoleError(Exception):
    """当前用户角色不支持工单列表访问。"""

class TicketNotFoundError(Exception):
    """工单不存在或当前用户无权查看。"""


class TicketAssignmentForbiddenError(Exception):
    """当前用户没有分配工单的权限。"""


class AssigneeNotFoundError(Exception):
    """指定的负责人不存在。"""


class AssigneeNotAgentError(Exception):
    """指定的负责人不是 AGENT 角色。"""


class TicketNotAssignableError(Exception):
    """工单当前状态不允许分配。"""


class TicketStatusTransitionForbiddenError(Exception):
    """当前用户没有权限执行该状态流转。"""


class TicketStatusTransitionNotAllowedError(Exception):
    """当前工单状态不允许转换到目标状态。"""

class TicketClosedForCommentError(Exception):
    """已关闭工单不允许新增评论。"""

# ============================================
# 工单状态流转规则
# ============================================

VALID_STATUS_TRANSITIONS = {
    ("ASSIGNED", "IN_PROGRESS"),
    ("IN_PROGRESS", "RESOLVED"),
    ("RESOLVED", "CLOSED"),
}

AGENT_STATUS_TRANSITIONS = {
    ("ASSIGNED", "IN_PROGRESS"),
    ("IN_PROGRESS", "RESOLVED"),
}

USER_STATUS_TRANSITIONS = {
    ("RESOLVED", "CLOSED"),
}



# ============================================
# 2. MySQL 命名锁
# ============================================

@contextmanager
def _ticket_number_lock(
    db: Session,
    lock_name: str,
) -> Iterator[None]:
    """
    使用独立数据库连接持有 MySQL 命名锁。

    锁必须一直持有到工单事务提交完成。
    """

    lock_connection = db.get_bind().connect()

    acquired = False

    try:

        result = lock_connection.execute(
            text("SELECT GET_LOCK(:lock_name, :timeout)"),
            {
                "lock_name": lock_name,
                "timeout": 10,
            },
        ).scalar_one()

        if result != 1:
            raise TicketNumberLockTimeoutError(
                "Could not acquire ticket number lock"
            )

        acquired = True

        yield

    finally:

        if acquired:

            try:

                released = lock_connection.execute(
                    text("SELECT RELEASE_LOCK(:lock_name)"),
                    {
                        "lock_name": lock_name,
                    },
                ).scalar_one()

                if released != 1:
                    lock_connection.invalidate()

            except SQLAlchemyError:

                # 避免将仍持有命名锁的连接放回连接池
                lock_connection.invalidate()

        try:
            lock_connection.close()

        except SQLAlchemyError:
            lock_connection.invalidate()


# ============================================
# 3. 生成下一个工单编号
# ============================================

def _next_ticket_number(
    db: Session,
    prefix: str,
) -> str:
    """
    查询当日最后一个工单编号，并生成下一个编号。

    示例：
        FD-20261123-00001
        FD-20261123-00002
    """

    latest_ticket_no = db.scalar(
        select(Ticket.ticket_no)
        .where(
            Ticket.ticket_no.like(
                f"{prefix}%"
            )
        )
        .order_by(
            Ticket.ticket_no.desc()
        )
        .limit(1)
    )

    # 当日第一张工单
    if latest_ticket_no is None:

        next_sequence = 1

    else:

        suffix = latest_ticket_no[len(prefix):]

        if not suffix.isascii() or not suffix.isdigit():

            raise TicketNumberGenerationError(
                "Invalid existing ticket number"
            )

        current_sequence = int(suffix)

        if current_sequence >= 99999:

            raise TicketNumberExhaustedError(
                "Daily ticket number limit reached"
            )

        next_sequence = current_sequence + 1

    return f"{prefix}{next_sequence:05d}"


# ============================================
# 4. 创建工单
# ============================================

def create_ticket(
    db: Session,
    ticket_data: TicketCreate,
    current_user: User,
) -> Ticket:
    """
    创建工单。

    1. 生成当日编号前缀。
    2. 获取 MySQL 命名锁。
    3. 检查分类是否存在。
    4. 生成唯一工单编号。
    5. 创建 Ticket ORM 对象。
    6. 创建 TicketHistory 历史记录。
    7. 在同一个事务中提交。
    8. 返回工单对象。
    """

    # ----------------------------------------
    # 生成 UTC 日期
    # ----------------------------------------

    now = datetime.now(timezone.utc)

    date_part = now.strftime("%Y%m%d")

    prefix = f"FD-{date_part}-"

    # ----------------------------------------
    # 生成数据库级命名锁名称
    # ----------------------------------------

    database_name = db.get_bind().url.database or ""

    database_key = sha256(
        database_name.encode("utf-8")
    ).hexdigest()[:12]

    lock_name = (
        f"flowdesk:{database_key}:ticket:{date_part}"
    )

    try:

        # ====================================
        # 持有编号锁，直到事务提交结束
        # ====================================

        with _ticket_number_lock(db, lock_name):

            # --------------------------------
            # 检查工单分类
            # --------------------------------

            category = db.get(
                Category,
                ticket_data.category_id,
            )

            if category is None:

                raise CategoryNotFoundError(
                    "Category does not exist"
                )

            # --------------------------------
            # 生成工单编号
            # --------------------------------

            ticket_no = _next_ticket_number(
                db,
                prefix,
            )

            # --------------------------------
            # 创建工单 ORM 对象
            # --------------------------------

            new_ticket = Ticket(
                ticket_no=ticket_no,
                title=ticket_data.title,
                description=ticket_data.description,
                priority=ticket_data.priority,

                status="OPEN",

                creator_id=current_user.id,
                assignee_id=None,

                category_id=ticket_data.category_id,

                deleted_at=None,
            )

            db.add(new_ticket)

            # 先写入工单，获取自增主键
            db.flush()

            # --------------------------------
            # 创建工单历史记录
            # --------------------------------

            history = TicketHistory(
                ticket_id=new_ticket.id,
                operator_id=current_user.id,

                action_type="CREATE",
                field_name="ticket",

                old_value=None,

                new_value={
                    "ticket_no": new_ticket.ticket_no,
                    "title": new_ticket.title,
                    "priority": new_ticket.priority,
                    "status": new_ticket.status,
                    "category_id": new_ticket.category_id,
                },
            )

            db.add(history)

            db.flush()

            # --------------------------------
            # 刷新工单对象
            # --------------------------------

            db.refresh(new_ticket)

            # --------------------------------
            # 提交事务
            # --------------------------------

            db.commit()

            return new_ticket

    except Exception:

        # 任意步骤失败，回滚当前事务
        db.rollback()

        raise


# ============================================
# 5. 查询工单列表
# ============================================

def list_tickets(
    db: Session,
    current_user: User,
    *,
    page: int = 1,
    page_size: int = 20,
    status: TicketStatus | None = None,
    priority: TicketPriority | None = None,
    category_id: int | None = None,
) -> tuple[list[Ticket], int]:
    """
    查询工单列表。

    1. 根据用户角色确定可见范围。
    2. 排除已经逻辑删除的工单。
    3. 根据条件筛选。
    4. 统计符合条件的工单数量。
    5. 执行分页查询。
    6. 按创建时间倒序排列。

    返回：
        工单列表、符合条件的总数量。
    """

    # ----------------------------------------
    # 1. 检查分页参数
    # ----------------------------------------

    if page < 1 or not 1 <= page_size <= 100:
        raise ValueError("Invalid pagination parameters")

    # ----------------------------------------
    # 2. 获取当前用户角色
    # ----------------------------------------

    role = current_user.role

    role_code = (
        role.code.strip().upper()
        if role is not None and isinstance(role.code, str)
        else None
    )

    # ----------------------------------------
    # 3. 基础查询条件
    # ----------------------------------------

    conditions = [
        Ticket.deleted_at.is_(None)
    ]

    # ----------------------------------------
    # 4. 根据角色限制工单可见范围
    # ----------------------------------------

    if role_code == "ADMIN":

        # 管理员查看所有未删除工单
        pass

    elif role_code == "AGENT":

        # 处理人员只能查看分配给自己的工单
        conditions.append(
            Ticket.assignee_id == current_user.id
        )

    elif role_code == "USER":

        # 普通用户只能查看自己创建的工单
        conditions.append(
            Ticket.creator_id == current_user.id
        )

    else:

        raise UnsupportedTicketRoleError(
            "Unsupported role for ticket listing"
        )

    # ----------------------------------------
    # 5. 状态筛选
    # ----------------------------------------

    if status is not None:

        conditions.append(
            Ticket.status == status
        )

    # ----------------------------------------
    # 6. 优先级筛选
    # ----------------------------------------

    if priority is not None:

        conditions.append(
            Ticket.priority == priority
        )

    # ----------------------------------------
    # 7. 分类筛选
    # ----------------------------------------

    if category_id is not None:

        conditions.append(
            Ticket.category_id == category_id
        )

    # ----------------------------------------
    # 8. 统计符合条件的工单数量
    # ----------------------------------------

    total = db.scalar(
        select(
            func.count(Ticket.id)
        ).where(
            *conditions
        )
    ) or 0

    # ----------------------------------------
    # 9. 分页查询
    # ----------------------------------------

    statement = (
        select(Ticket)
        .where(*conditions)
        .order_by(
            Ticket.created_at.desc(),
            Ticket.id.desc(),
        )
        .offset(
            (page - 1) * page_size
        )
        .limit(page_size)
    )

    tickets = db.scalars(
        statement
    ).all()

    # ----------------------------------------
    # 10. 返回结果
    # ----------------------------------------

    return list(tickets), int(total)

# ============================================
# 6. 查询工单详情
# ============================================

def get_ticket(
    db: Session,
    current_user: User,
    ticket_id: int,
) -> Ticket:
    """
    查询工单详情。

    1. 获取当前用户角色。
    2. 根据角色确定工单访问范围。
    3. 排除已经逻辑删除的工单。
    4. 查询指定工单。
    5. 无权访问或工单不存在时返回统一异常。
    """

    # ----------------------------------------
    # 1. 获取当前用户角色
    # ----------------------------------------

    role = current_user.role

    role_code = (
        role.code.strip().upper()
        if role is not None and isinstance(role.code, str)
        else None
    )

    # ----------------------------------------
    # 2. 基础查询条件
    # ----------------------------------------

    conditions = [
        Ticket.id == ticket_id,
        Ticket.deleted_at.is_(None),
    ]

    # ----------------------------------------
    # 3. 根据角色限制访问范围
    # ----------------------------------------

    if role_code == "ADMIN":

        # 管理员可以查看所有有效工单
        pass

    elif role_code == "AGENT":

        # 处理人员只能查看分配给自己的工单
        conditions.append(
            Ticket.assignee_id == current_user.id
        )

    elif role_code == "USER":

        # 普通用户只能查看自己创建的工单
        conditions.append(
            Ticket.creator_id == current_user.id
        )

    else:

        raise UnsupportedTicketRoleError(
            "Unsupported role for ticket access"
        )

    # ----------------------------------------
    # 4. 查询工单
    # ----------------------------------------

    ticket = db.scalar(
        select(Ticket).where(
            *conditions
        )
    )

    # ----------------------------------------
    # 5. 不存在或无权访问
    # ----------------------------------------

    if ticket is None:

        raise TicketNotFoundError(
            "Ticket not found"
        )

    return ticket


# ============================================
# 7. 修改工单
# ============================================

def update_ticket(
    db: Session,
    ticket_data: TicketUpdate,
    current_user: User,
    ticket_id: int,
) -> Ticket:
    """
    修改工单。

    1. 根据角色确定修改权限。
    2. 使用 SELECT FOR UPDATE 锁定工单。
    3. 查询并验证工单分类。
    4. 只修改客户端实际提交的字段。
    5. 为每个发生变化的字段创建历史记录。
    6. 在同一个事务中提交工单和历史记录。
    """

    try:

        # ------------------------------------
        # 1. 获取当前用户角色
        # ------------------------------------

        role = current_user.role

        role_code = (
            role.code.strip().upper()
            if role is not None
            and isinstance(role.code, str)
            else None
        )

        # ------------------------------------
        # 2. 构建权限条件
        # ------------------------------------

        conditions = [
            Ticket.id == ticket_id,
            Ticket.deleted_at.is_(None),
        ]

        if role_code == "ADMIN":

            pass

        elif role_code == "AGENT":

            conditions.append(
                Ticket.assignee_id == current_user.id
            )

        elif role_code == "USER":

            conditions.extend([
                Ticket.creator_id == current_user.id,
                Ticket.status == "OPEN",
            ])

        else:

            raise UnsupportedTicketRoleError(
                "Unsupported role for ticket update"
            )

        # ------------------------------------
        # 3. 查询并锁定工单
        # ------------------------------------

        ticket = db.scalar(
            select(Ticket)
            .where(*conditions)
            .with_for_update()
            .execution_options(
                populate_existing=True
            )
        )

        if ticket is None:

            raise TicketNotFoundError(
                "Ticket not found"
            )

        # ------------------------------------
        # 4. 获取客户端实际提交的字段
        # ------------------------------------

        changes = ticket_data.model_dump(
            exclude_unset=True
        )

        # ------------------------------------
        # 5. 验证分类是否存在
        # ------------------------------------

        if "category_id" in changes:

            category = db.get(
                Category,
                changes["category_id"],
            )

            if category is None:

                raise CategoryNotFoundError(
                    "Category does not exist"
                )

        # ------------------------------------
        # 6. 修改字段并创建历史记录
        # ------------------------------------

        for field_name, new_value in changes.items():

            old_value = getattr(
                ticket,
                field_name,
            )

            # 值没有发生变化，不记录历史
            if old_value == new_value:
                continue

            # 修改工单字段
            setattr(
                ticket,
                field_name,
                new_value,
            )

            # 创建对应的历史记录
            history = TicketHistory(
                ticket_id=ticket.id,
                operator_id=current_user.id,

                action_type="UPDATE",
                field_name=field_name,

                old_value=old_value,
                new_value=new_value,
            )

            db.add(history)

        # ------------------------------------
        # 7. 提交事务
        # ------------------------------------

        db.flush()

        db.commit()

        # ------------------------------------
        # 8. 刷新 ORM 对象
        # ------------------------------------

        db.refresh(ticket)

        return ticket

    except Exception:

        db.rollback()

        raise



# ============================================
# 8. 分配工单负责人
# ============================================

def assign_ticket(
    db: Session,
    ticket_id: int,
    assignee_id: int,
    current_user: User,
) -> Ticket:
    """
    分配工单负责人。

    1. 验证当前用户是否为 ADMIN。
    2. 使用 SELECT FOR UPDATE 锁定工单。
    3. 验证工单是否可以分配。
    4. 查询指定负责人。
    5. 验证负责人是否为 AGENT。
    6. 修改 assignee_id 和 status。
    7. 创建两条操作历史记录。
    8. 在同一个事务中提交。
    """

    try:

        # ------------------------------------
        # 1. 验证当前用户角色
        # ------------------------------------

        role = current_user.role

        role_code = (
            role.code.strip().upper()
            if role is not None
            and isinstance(role.code, str)
            else None
        )

        if role_code != "ADMIN":

            raise TicketAssignmentForbiddenError(
                "Only ADMIN can assign tickets"
            )

        # ------------------------------------
        # 2. 锁定工单
        # ------------------------------------

        ticket = db.scalar(
            select(Ticket)
            .where(
                Ticket.id == ticket_id,
                Ticket.deleted_at.is_(None),
            )
            .with_for_update()
            .execution_options(
                populate_existing=True
            )
        )

        if ticket is None:

            raise TicketNotFoundError(
                "Ticket not found"
            )

        # ------------------------------------
        # 3. 检查工单状态
        # ------------------------------------

        if (
            ticket.status != "OPEN"
            or ticket.assignee_id is not None
        ):

            raise TicketNotAssignableError(
                "Ticket is not available for assignment"
            )

        # ------------------------------------
        # 4. 查询负责人
        # ------------------------------------

        assignee = db.get(
            User,
            assignee_id,
        )

        if assignee is None:

            raise AssigneeNotFoundError(
                "Assignee does not exist"
            )

        # ------------------------------------
        # 5. 验证负责人角色
        # ------------------------------------

        assignee_role = assignee.role

        assignee_role_code = (
            assignee_role.code.strip().upper()
            if assignee_role is not None
            and isinstance(assignee_role.code, str)
            else None
        )

        if assignee_role_code != "AGENT":

            raise AssigneeNotAgentError(
                "Assignee must have AGENT role"
            )

        # ------------------------------------
        # 6. 保存修改前的数据
        # ------------------------------------

        old_assignee_id = ticket.assignee_id
        old_status = ticket.status

        # ------------------------------------
        # 7. 修改工单
        # ------------------------------------

        ticket.assignee_id = assignee.id
        ticket.status = "ASSIGNED"

        # ------------------------------------
        # 8. 创建负责人变更历史
        # ------------------------------------

        assignee_history = TicketHistory(
            ticket_id=ticket.id,
            operator_id=current_user.id,

            action_type="ASSIGN",
            field_name="assignee_id",

            old_value=old_assignee_id,
            new_value=assignee.id,
        )

        db.add(assignee_history)

        # ------------------------------------
        # 9. 创建状态变更历史
        # ------------------------------------

        status_history = TicketHistory(
            ticket_id=ticket.id,
            operator_id=current_user.id,

            action_type="ASSIGN",
            field_name="status",

            old_value=old_status,
            new_value="ASSIGNED",
        )

        db.add(status_history)

        # ------------------------------------
        # 10. 提交事务
        # ------------------------------------

        db.flush()

        db.commit()

        # ------------------------------------
        # 11. 刷新工单对象
        # ------------------------------------

        db.refresh(ticket)

        return ticket

    except Exception:

        db.rollback()

        raise



# ============================================
# 9. 工单状态流转
# ============================================

def transition_ticket_status(
    db: Session,
    ticket_id: int,
    target_status: TicketStatus,
    current_user: User,
) -> Ticket:
    """
    修改工单状态。

    1. 获取当前用户角色。
    2. 使用 SELECT FOR UPDATE 锁定工单。
    3. 验证工单访问权限。
    4. 验证状态流转是否合法。
    5. 验证角色是否允许执行该流转。
    6. 修改工单状态。
    7. 创建操作历史记录。
    8. 在同一个事务中提交。
    """

    try:

        # ------------------------------------
        # 1. 获取当前用户角色
        # ------------------------------------

        role = current_user.role

        role_code = (
            role.code.strip().upper()
            if role is not None
            and isinstance(role.code, str)
            else None
        )

        # ------------------------------------
        # 2. 锁定工单
        # ------------------------------------

        ticket = db.scalar(
            select(Ticket)
            .where(
                Ticket.id == ticket_id,
                Ticket.deleted_at.is_(None),
            )
            .with_for_update()
            .execution_options(
                populate_existing=True
            )
        )

        if ticket is None:

            raise TicketNotFoundError(
                "Ticket not found"
            )

        # ------------------------------------
        # 3. 验证工单访问权限
        # ------------------------------------

        if role_code == "ADMIN":

            pass

        elif role_code == "AGENT":

            if ticket.assignee_id != current_user.id:

                raise TicketStatusTransitionForbiddenError(
                    "Agent can only operate assigned tickets"
                )

        elif role_code == "USER":

            if ticket.creator_id != current_user.id:

                raise TicketStatusTransitionForbiddenError(
                    "User can only operate created tickets"
                )

        else:

            raise TicketStatusTransitionForbiddenError(
                "Unsupported role"
            )

        # ------------------------------------
        # 4. 保存修改前的状态
        # ------------------------------------

        old_status = ticket.status

        # ------------------------------------
        # 5. 检查状态转换是否合法
        # ------------------------------------

        transition = (
            old_status,
            target_status,
        )

        if transition not in VALID_STATUS_TRANSITIONS:

            raise TicketStatusTransitionNotAllowedError(
                f"Cannot transition from "
                f"{old_status} to {target_status}"
            )

        # ------------------------------------
        # 6. 检查角色是否允许执行该转换
        # ------------------------------------

        if role_code == "ADMIN":

            pass

        elif role_code == "AGENT":

            if transition not in AGENT_STATUS_TRANSITIONS:

                raise TicketStatusTransitionForbiddenError(
                    "Agent cannot perform this status transition"
                )

        elif role_code == "USER":

            if transition not in USER_STATUS_TRANSITIONS:

                raise TicketStatusTransitionForbiddenError(
                    "User cannot perform this status transition"
                )

        # ------------------------------------
        # 7. 修改工单状态
        # ------------------------------------

        ticket.status = target_status

        # ------------------------------------
        # 8. 创建状态变更历史
        # ------------------------------------

        history = TicketHistory(
            ticket_id=ticket.id,
            operator_id=current_user.id,

            action_type="STATUS_CHANGE",
            field_name="status",

            old_value=old_status,
            new_value=target_status,
        )

        db.add(history)

        # ------------------------------------
        # 9. 提交事务
        # ------------------------------------

        db.flush()

        db.commit()

        # ------------------------------------
        # 10. 刷新 ORM 对象
        # ------------------------------------

        db.refresh(ticket)

        return ticket

    except Exception:

        db.rollback()

        raise


# ============================================
# 10. 创建工单评论
# ============================================

def create_ticket_comment(
    db: Session,
    ticket_id: int,
    comment_data: TicketCommentCreate,
    current_user: User,
) -> TicketComment:
    """
    创建工单评论。

    1. 获取当前用户角色。
    2. 锁定工单。
    3. 验证用户是否有权访问工单。
    4. 检查工单是否已经关闭。
    5. 创建评论 ORM 对象。
    6. 提交事务。
    """

    try:

        # ------------------------------------
        # 1. 获取用户角色
        # ------------------------------------

        role = current_user.role

        role_code = (
            role.code.strip().upper()
            if role is not None
            and isinstance(role.code, str)
            else None
        )

        # ------------------------------------
        # 2. 构建工单访问条件
        # ------------------------------------

        conditions = [
            Ticket.id == ticket_id,
            Ticket.deleted_at.is_(None),
        ]

        if role_code == "ADMIN":

            pass

        elif role_code == "AGENT":

            conditions.append(
                Ticket.assignee_id == current_user.id
            )

        elif role_code == "USER":

            conditions.append(
                Ticket.creator_id == current_user.id
            )

        else:

            raise UnsupportedTicketRoleError(
                "Unsupported role for commenting"
            )

        # ------------------------------------
        # 3. 锁定工单
        # ------------------------------------

        ticket = db.scalar(
            select(Ticket)
            .where(*conditions)
            .with_for_update()
            .execution_options(
                populate_existing=True
            )
        )

        if ticket is None:

            raise TicketNotFoundError(
                "Ticket not found"
            )

        # ------------------------------------
        # 4. 检查工单状态
        # ------------------------------------

        if ticket.status == "CLOSED":

            raise TicketClosedForCommentError(
                "Closed ticket does not accept new comments"
            )

        # ------------------------------------
        # 5. 创建评论
        # ------------------------------------

        new_comment = TicketComment(
            ticket_id=ticket.id,
            user_id=current_user.id,
            content=comment_data.content,
        )

        db.add(new_comment)

        # ------------------------------------
        # 6. 提交事务
        # ------------------------------------

        db.flush()

        db.commit()

        # ------------------------------------
        # 7. 刷新对象
        # ------------------------------------

        db.refresh(new_comment)

        return new_comment

    except Exception:

        db.rollback()

        raise


# ============================================
# 11. 查询工单评论
# ============================================

def list_ticket_comments(
    db: Session,
    current_user: User,
    ticket_id: int,
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[TicketComment], int]:
    """
    查询工单评论。

    1. 验证分页参数。
    2. 验证用户是否有权访问工单。
    3. 统计评论总数。
    4. 按创建时间正序查询。
    5. 执行分页。
    6. 返回评论列表和总数。
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
    # 3. 统计评论数量
    # ----------------------------------------

    total = db.scalar(
        select(
            func.count(TicketComment.id)
        ).where(
            TicketComment.ticket_id == ticket.id
        )
    ) or 0

    # ----------------------------------------
    # 4. 分页查询评论
    # ----------------------------------------

    statement = (
        select(TicketComment)
        .where(
            TicketComment.ticket_id == ticket.id
        )
        .order_by(
            TicketComment.created_at.asc(),
            TicketComment.id.asc(),
        )
        .offset(
            (page - 1) * page_size
        )
        .limit(page_size)
    )

    comments = db.scalars(
        statement
    ).all()

    # ----------------------------------------
    # 5. 返回结果
    # ----------------------------------------

    return list(comments), int(total)
