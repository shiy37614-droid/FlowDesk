
from datetime import datetime, timedelta

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
import app.models

from app.models import (
    Category,
    Role,
    Ticket,
    User,
)

from app.db.session import get_db
from app.api.deps import get_current_user
from app.api.v1.tickets import router as tickets_router





from pydantic import ValidationError

from sqlalchemy import select

from app.models.ticket_history import TicketHistory

from app.schemas.ticket import TicketUpdate
from app.schemas.ticket import TicketAssign

from app.services.ticket_service import (
    list_tickets,
    get_ticket,
    update_ticket,
    UnsupportedTicketRoleError,
    TicketNotFoundError,
    CategoryNotFoundError,
)

from app.services.ticket_service import (
    assign_ticket,
    TicketAssignmentForbiddenError,
    AssigneeNotFoundError,
    AssigneeNotAgentError,
    TicketNotAssignableError,
)
from app.schemas.ticket import TicketStatusUpdate
from app.models.ticket_comment import TicketComment

from app.schemas.ticket_comment import TicketCommentCreate

from app.services.ticket_service import (
    create_ticket_comment,
    list_ticket_comments,
    TicketClosedForCommentError,
)
# ============================================
# 1. 测试数据库
# ============================================

@pytest.fixture
def db():

    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )

    # 仅在 SQLite 测试环境中兼容 MySQL 的自动更新时间语法
    @event.listens_for(
        engine,
        "before_cursor_execute",
        retval=True,
    )
    def adapt_mysql_timestamp_for_sqlite(
        conn,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ):
        if statement.lstrip().upper().startswith("CREATE TABLE"):
            statement = statement.replace(
                "DEFAULT (CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP)",
                "DEFAULT CURRENT_TIMESTAMP",
            )

        return statement, parameters

    Base.metadata.create_all(engine)

    with Session(engine) as session:

        # 创建角色
        session.add_all([
            Role(
                id=1,
                name="管理员",
                code="ADMIN",
            ),
            Role(
                id=2,
                name="处理人员",
                code="AGENT",
            ),
            Role(
                id=3,
                name="普通用户",
                code="USER",
            ),
        ])

        session.flush()

        # 创建用户
        session.add_all([
            User(
                id=1,
                username="admin",
                password_hash="test-hash",
                display_name="管理员",
                role_id=1,
            ),
            User(
                id=2,
                username="agent",
                password_hash="test-hash",
                display_name="处理人员",
                role_id=2,
            ),
            User(
                id=3,
                username="user_a",
                password_hash="test-hash",
                display_name="用户甲",
                role_id=3,
            ),
            User(
                id=4,
                username="user_b",
                password_hash="test-hash",
                display_name="用户乙",
                role_id=3,
            ),
        ])

        session.add(
            Category(
                id=10,
                name="网络问题",
            )
        )

        session.flush()

        now = datetime(2026, 11, 24, 4, 0)

        # 创建测试工单
        session.add_all([

            Ticket(
                id=1,
                ticket_no="FD-TEST-00001",
                title="用户甲的工单",
                description="网络故障",
                priority="HIGH",
                status="OPEN",
                creator_id=3,
                assignee_id=None,
                category_id=10,
                deleted_at=None,
                created_at=now,
                updated_at=now,
            ),

            Ticket(
                id=2,
                ticket_no="FD-TEST-00002",
                title="用户乙的已分配工单",
                description="电脑故障",
                priority="NORMAL",
                status="ASSIGNED",
                creator_id=4,
                assignee_id=2,
                category_id=10,
                deleted_at=None,
                created_at=now + timedelta(seconds=1),
                updated_at=now,
            ),

            Ticket(
                id=3,
                ticket_no="FD-TEST-00003",
                title="用户乙的处理中工单",
                description="网络故障",
                priority="HIGH",
                status="IN_PROGRESS",
                creator_id=4,
                assignee_id=2,
                category_id=10,
                deleted_at=None,
                created_at=now + timedelta(seconds=2),
                updated_at=now,
            ),

            Ticket(
                id=4,
                ticket_no="FD-TEST-00004",
                title="已经删除的工单",
                description="测试逻辑删除",
                priority="HIGH",
                status="OPEN",
                creator_id=3,
                assignee_id=None,
                category_id=10,
                deleted_at=now + timedelta(seconds=3),
                created_at=now + timedelta(seconds=3),
                updated_at=now,
            ),

            Ticket(
                id=5,
                ticket_no="FD-TEST-00005",
                title="用户甲的已分配工单",
                description="网络问题",
                priority="NORMAL",
                status="ASSIGNED",
                creator_id=3,
                assignee_id=2,
                category_id=10,
                deleted_at=None,
                created_at=now + timedelta(seconds=4),
                updated_at=now,
            ),

        ])

        session.commit()

        yield session

    engine.dispose()


# ============================================
# 2. USER 只能查看自己创建的工单
# ============================================

def test_user_sees_only_own_active_tickets(db):

    user = db.get(User, 3)

    tickets, total = list_tickets(
        db,
        user,
    )

    assert total == 2

    assert [
        ticket.id for ticket in tickets
    ] == [5, 1]


# ============================================
# 3. AGENT 只能查看分配给自己的工单
# ============================================

def test_agent_sees_only_assigned_active_tickets(db):

    agent = db.get(User, 2)

    tickets, total = list_tickets(
        db,
        agent,
    )

    assert total == 3

    assert [
        ticket.id for ticket in tickets
    ] == [5, 3, 2]


# ============================================
# 4. ADMIN 查看所有有效工单
# ============================================

def test_admin_sees_all_active_tickets(db):

    admin = db.get(User, 1)

    tickets, total = list_tickets(
        db,
        admin,
    )

    assert total == 4

    assert [
        ticket.id for ticket in tickets
    ] == [5, 3, 2, 1]


# ============================================
# 5. 多条件筛选和分页
# ============================================

def test_filters_and_pagination(db):

    admin = db.get(User, 1)

    tickets, total = list_tickets(
        db,
        admin,
        status="OPEN",
        priority="HIGH",
        category_id=10,
    )

    assert total == 1

    assert tickets[0].id == 1

    # 第一页
    page1, total = list_tickets(
        db,
        admin,
        page=1,
        page_size=2,
    )

    # 第二页
    page2, _ = list_tickets(
        db,
        admin,
        page=2,
        page_size=2,
    )

    # 超出范围的页
    page3, _ = list_tickets(
        db,
        admin,
        page=3,
        page_size=2,
    )

    assert total == 4

    assert [t.id for t in page1] == [5, 3]

    assert [t.id for t in page2] == [2, 1]

    assert page3 == []


# ============================================
# 6. 未知角色拒绝访问
# ============================================

def test_unknown_role_is_rejected(db):

    db.add(
        Role(
            id=9,
            name="未知角色",
            code="ROOT",
        )
    )

    db.flush()

    db.add(
        User(
            id=9,
            username="root",
            password_hash="test-hash",
            display_name="Root",
            role_id=9,
        )
    )

    db.commit()

    user = db.get(User, 9)

    with pytest.raises(UnsupportedTicketRoleError):

        list_tickets(
            db,
            user,
        )


# ============================================
# 7. HTTP 分页接口测试
# ============================================

def test_http_list_endpoint_returns_paginated_data(db):

    admin = db.get(User, 1)

    app = FastAPI()

    app.include_router(
        tickets_router,
        prefix="/api/v1",
    )

    app.dependency_overrides[get_db] = lambda: db

    app.dependency_overrides[get_current_user] = (
        lambda: admin
    )

    try:

        with TestClient(app) as client:

            response = client.get(
                "/api/v1/tickets?page=1&page_size=1&priority=HIGH"
            )

        assert response.status_code == 200

        body = response.json()

        assert body["total"] == 2
        assert body["page"] == 1
        assert body["page_size"] == 1
        assert body["total_pages"] == 2

        assert len(body["items"]) == 1

        assert "password_hash" not in body["items"][0]

    finally:

        app.dependency_overrides.clear()


# ============================================
# 8. 非法分页参数测试
# ============================================

def test_http_list_endpoint_rejects_invalid_page(db):

    admin = db.get(User, 1)

    app = FastAPI()

    app.include_router(
        tickets_router,
        prefix="/api/v1",
    )

    app.dependency_overrides[get_db] = lambda: db

    app.dependency_overrides[get_current_user] = (
        lambda: admin
    )

    try:

        with TestClient(app) as client:

            response = client.get(
                "/api/v1/tickets?page=0"
            )

        assert response.status_code == 422

    finally:

        app.dependency_overrides.clear()


# ============================================
# 9. USER 可以查看自己的工单
# ============================================

def test_user_can_view_own_ticket(db):

    user = db.get(User, 3)

    ticket = get_ticket(
        db,
        user,
        1,
    )

    assert ticket.id == 1
    assert ticket.creator_id == 3


# ============================================
# 10. USER 不能查看别人的工单
# ============================================

def test_user_cannot_view_others_ticket(db):

    user = db.get(User, 3)

    with pytest.raises(TicketNotFoundError):

        get_ticket(
            db,
            user,
            2,
        )


# ============================================
# 11. AGENT 可以查看分配给自己的工单
# ============================================

def test_agent_can_view_assigned_ticket(db):

    agent = db.get(User, 2)

    ticket = get_ticket(
        db,
        agent,
        2,
    )

    assert ticket.id == 2
    assert ticket.assignee_id == 2


# ============================================
# 12. AGENT 不能查看未分配给自己的工单
# ============================================

def test_agent_cannot_view_unassigned_ticket(db):

    agent = db.get(User, 2)

    with pytest.raises(TicketNotFoundError):

        get_ticket(
            db,
            agent,
            1,
        )


# ============================================
# 13. ADMIN 可以查看其他用户的工单
# ============================================

def test_admin_can_view_any_active_ticket(db):

    admin = db.get(User, 1)

    ticket = get_ticket(
        db,
        admin,
        1,
    )

    assert ticket.id == 1


# ============================================
# 14. 不能查看逻辑删除的工单
# ============================================

def test_deleted_ticket_cannot_be_viewed(db):

    admin = db.get(User, 1)

    with pytest.raises(TicketNotFoundError):

        get_ticket(
            db,
            admin,
            4,
        )



# ============================================
# 15. Schema 正常数据验证
# ============================================

def test_ticket_update_schema_normalizes_data():

    data = TicketUpdate(
        title="  新的工单标题  ",
        priority=" high ",
    )

    assert data.title == "新的工单标题"
    assert data.priority == "HIGH"

    assert data.model_dump(
        exclude_unset=True
    ) == {
        "title": "新的工单标题",
        "priority": "HIGH",
    }


# ============================================
# 16. Schema 非法数据验证
# ============================================

@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"title": None},
        {"title": "   "},
        {"priority": "URGENT"},
        {"category_id": "10"},
        {"status": "CLOSED"},
        {"creator_id": 5},
        {"assignee_id": 5},
    ],
)
def test_ticket_update_schema_rejects_invalid_data(payload):

    with pytest.raises(ValidationError):

        TicketUpdate(**payload)


# ============================================
# 17. USER 修改自己的 OPEN 工单
# ============================================

def test_user_can_update_own_open_ticket(db):

    user = db.get(User, 3)

    ticket = update_ticket(
        db=db,
        ticket_data=TicketUpdate(
            title="新的网络故障",
            priority="HIGH",
        ),
        current_user=user,
        ticket_id=1,
    )

    assert ticket.title == "新的网络故障"
    assert ticket.priority == "HIGH"

    histories = db.scalars(
        select(TicketHistory).where(
            TicketHistory.ticket_id == 1
        )
    ).all()

    assert len(histories) == 1

    history_map = {
        item.field_name: (
            item.old_value,
            item.new_value,
        )
        for item in histories
    }

    assert history_map["title"] == (
        "用户甲的工单",
        "新的网络故障",
    )

    assert set(history_map) == {"title"}

# ============================================
# 18. USER 不能修改别人的工单
# ============================================

def test_user_cannot_update_others_ticket(db):

    user = db.get(User, 3)

    with pytest.raises(TicketNotFoundError):

        update_ticket(
            db,
            TicketUpdate(title="非法修改"),
            user,
            2,
        )


# ============================================
# 19. USER 不能修改非 OPEN 工单
# ============================================

def test_user_cannot_update_assigned_ticket(db):

    user = db.get(User, 3)

    with pytest.raises(TicketNotFoundError):

        update_ticket(
            db,
            TicketUpdate(title="非法修改"),
            user,
            5,
        )


# ============================================
# 20. AGENT 可以修改分配给自己的工单
# ============================================

def test_agent_can_update_assigned_ticket(db):

    agent = db.get(User, 2)

    ticket = update_ticket(
        db,
        TicketUpdate(
            title="处理人员更新标题"
        ),
        agent,
        2,
    )

    assert ticket.title == "处理人员更新标题"


# ============================================
# 21. AGENT 不能修改未分配给自己的工单
# ============================================

def test_agent_cannot_update_unassigned_ticket(db):

    agent = db.get(User, 2)

    with pytest.raises(TicketNotFoundError):

        update_ticket(
            db,
            TicketUpdate(title="非法修改"),
            agent,
            1,
        )


# ============================================
# 22. ADMIN 可以修改其他用户的工单
# ============================================

def test_admin_can_update_any_active_ticket(db):

    admin = db.get(User, 1)

    ticket = update_ticket(
        db,
        TicketUpdate(
            title="管理员修改标题"
        ),
        admin,
        1,
    )

    assert ticket.title == "管理员修改标题"


# ============================================
# 23. 分类不存在时回滚
# ============================================

def test_missing_category_rolls_back(db):

    user = db.get(User, 3)

    with pytest.raises(CategoryNotFoundError):

        update_ticket(
            db,
            TicketUpdate(
                title="不应该保存的标题",
                category_id=999,
            ),
            user,
            1,
        )

    ticket = db.get(Ticket, 1)

    assert ticket.title == "用户甲的工单"
    assert ticket.category_id == 10

    histories = db.scalars(
        select(TicketHistory).where(
            TicketHistory.ticket_id == 1
        )
    ).all()

    assert histories == []


# ============================================
# 24. 已经逻辑删除的工单不能修改
# ============================================

def test_deleted_ticket_cannot_be_updated(db):

    admin = db.get(User, 1)

    with pytest.raises(TicketNotFoundError):

        update_ticket(
            db,
            TicketUpdate(
                title="不应该修改"
            ),
            admin,
            4,
        )


# ============================================
# 25. 提交相同值不产生多余历史记录
# ============================================

def test_unchanged_value_does_not_create_history(db):

    user = db.get(User, 3)

    ticket = update_ticket(
        db,
        TicketUpdate(
            title="用户甲的工单"
        ),
        user,
        1,
    )

    assert ticket.title == "用户甲的工单"

    histories = db.scalars(
        select(TicketHistory).where(
            TicketHistory.ticket_id == 1
        )
    ).all()

    assert histories == []


# ============================================
# 26. PATCH HTTP 接口测试
# ============================================

def test_http_patch_ticket_endpoint(db):

    admin = db.get(User, 1)

    app = FastAPI()

    app.include_router(
        tickets_router,
        prefix="/api/v1",
    )

    app.dependency_overrides[get_db] = lambda: db

    app.dependency_overrides[get_current_user] = (
        lambda: admin
    )

    try:

        with TestClient(app) as client:

            response = client.patch(
                "/api/v1/tickets/1",
                json={
                    "title": "HTTP 修改后的标题",
                    "priority": "HIGH",
                },
            )

        assert response.status_code == 200

        body = response.json()

        assert body["title"] == "HTTP 修改后的标题"
        assert body["priority"] == "HIGH"

        assert body["id"] == 1

        assert "password_hash" not in body

    finally:

        app.dependency_overrides.clear()



# ============================================
# 27. TicketAssign Schema 正常验证
# ============================================

def test_ticket_assign_schema_valid():

    data = TicketAssign(
        assignee_id=2
    )

    assert data.assignee_id == 2


# ============================================
# 28. TicketAssign Schema 非法数据验证
# ============================================

@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"assignee_id": 0},
        {"assignee_id": -1},
        {"assignee_id": "2"},
        {"assignee_id": None},
        {"assignee_id": 2, "status": "ASSIGNED"},
    ],
)
def test_ticket_assign_schema_rejects_invalid_data(payload):

    with pytest.raises(ValidationError):

        TicketAssign(**payload)


# ============================================
# 29. ADMIN 可以成功分配工单
# ============================================

def test_admin_can_assign_ticket(db):

    admin = db.get(User, 1)

    ticket = assign_ticket(
        db=db,
        ticket_id=1,
        assignee_id=2,
        current_user=admin,
    )

    assert ticket.assignee_id == 2
    assert ticket.status == "ASSIGNED"

    # 检查两条历史记录
    histories = db.scalars(
        select(TicketHistory)
        .where(
            TicketHistory.ticket_id == 1
        )
        .order_by(TicketHistory.id)
    ).all()

    assert len(histories) == 2

    history_data = [
        (
            item.action_type,
            item.field_name,
            item.old_value,
            item.new_value,
        )
        for item in histories
    ]

    assert history_data == [
        ("ASSIGN", "assignee_id", None, 2),
        ("ASSIGN", "status", "OPEN", "ASSIGNED"),
    ]


# ============================================
# 30. USER 不能分配工单
# ============================================

def test_user_cannot_assign_ticket(db):

    user = db.get(User, 3)

    with pytest.raises(
        TicketAssignmentForbiddenError
    ):

        assign_ticket(
            db,
            1,
            2,
            user,
        )


# ============================================
# 31. AGENT 不能分配工单
# ============================================

def test_agent_cannot_assign_ticket(db):

    agent = db.get(User, 2)

    with pytest.raises(
        TicketAssignmentForbiddenError
    ):

        assign_ticket(
            db,
            1,
            2,
            agent,
        )


# ============================================
# 32. 不能分配给普通 USER
# ============================================

def test_cannot_assign_to_normal_user(db):

    admin = db.get(User, 1)

    with pytest.raises(
        AssigneeNotAgentError
    ):

        assign_ticket(
            db,
            1,
            3,
            admin,
        )

    # 验证工单没有被修改
    ticket = db.get(Ticket, 1)

    assert ticket.status == "OPEN"
    assert ticket.assignee_id is None


# ============================================
# 33. 负责人不存在
# ============================================

def test_assignee_not_found(db):

    admin = db.get(User, 1)

    with pytest.raises(
        AssigneeNotFoundError
    ):

        assign_ticket(
            db,
            1,
            999,
            admin,
        )


# ============================================
# 34. 已经分配的工单不能重复分配
# ============================================

def test_cannot_assign_already_assigned_ticket(db):

    admin = db.get(User, 1)

    with pytest.raises(
        TicketNotAssignableError
    ):

        assign_ticket(
            db,
            2,
            2,
            admin,
        )


# ============================================
# 35. 已删除工单不能分配
# ============================================

def test_cannot_assign_deleted_ticket(db):

    admin = db.get(User, 1)

    with pytest.raises(
        TicketNotFoundError
    ):

        assign_ticket(
            db,
            4,
            2,
            admin,
        )


# ============================================
# 工单状态 Schema 专项测试
# ============================================

def test_ticket_status_update_schema():

    # 正常状态
    data = TicketStatusUpdate(
        status="IN_PROGRESS"
    )

    assert data.status == "IN_PROGRESS"

    # 自动规范化
    data = TicketStatusUpdate(
        status=" resolved "
    )

    assert data.status == "RESOLVED"

    # 不允许非法状态
    with pytest.raises(ValidationError):

        TicketStatusUpdate(
            status="CANCELLED"
        )

    # 不允许提交额外字段
    with pytest.raises(ValidationError):

        TicketStatusUpdate(
            status="CLOSED",
            assignee_id=9,
        )

    # 不允许缺少状态
    with pytest.raises(ValidationError):

        TicketStatusUpdate()

    # 不允许数字类型
    with pytest.raises(ValidationError):

        TicketStatusUpdate(
            status=123
        )


# ============================================
# Ticket Comment 专项测试
# ============================================


# ============================================
# 48. 评论 Schema 验证
# ============================================

def test_ticket_comment_schema_validation():

    # 正常内容
    data = TicketCommentCreate(
        content="  网络仍然无法连接  "
    )

    assert data.content == "网络仍然无法连接"

    # 最大长度允许 5000
    data = TicketCommentCreate(
        content="x" * 5000
    )

    assert len(data.content) == 5000

    # 非法内容
    invalid_payloads = [
        {"content": ""},
        {"content": "   "},
        {"content": "x" * 5001},
        {"content": "正常评论", "user_id": 3},
        {},
    ]

    for payload in invalid_payloads:

        with pytest.raises(ValidationError):

            TicketCommentCreate(**payload)


# ============================================
# 49. USER 可以评论自己的工单
# ============================================

def test_user_can_create_own_ticket_comment(db):

    user = db.get(User, 3)

    comment = create_ticket_comment(
        db=db,
        ticket_id=1,
        comment_data=TicketCommentCreate(
            content="网络问题仍然存在"
        ),
        current_user=user,
    )

    assert comment.id is not None
    assert comment.ticket_id == 1
    assert comment.user_id == 3
    assert comment.content == "网络问题仍然存在"

    saved_comment = db.get(
        TicketComment,
        comment.id,
    )

    assert saved_comment is not None


# ============================================
# 50. AGENT 可以评论分配给自己的工单
# ============================================

def test_agent_can_create_assigned_ticket_comment(db):

    agent = db.get(User, 2)

    comment = create_ticket_comment(
        db=db,
        ticket_id=2,
        comment_data=TicketCommentCreate(
            content="正在检查网络设备"
        ),
        current_user=agent,
    )

    assert comment.ticket_id == 2
    assert comment.user_id == 2


# ============================================
# 51. ADMIN 可以评论其他用户的工单
# ============================================

def test_admin_can_create_any_ticket_comment(db):

    admin = db.get(User, 1)

    comment = create_ticket_comment(
        db=db,
        ticket_id=3,
        comment_data=TicketCommentCreate(
            content="管理员补充说明"
        ),
        current_user=admin,
    )

    assert comment.ticket_id == 3
    assert comment.user_id == 1


# ============================================
# 52. USER 不能评论别人的工单
# ============================================

def test_user_cannot_comment_others_ticket(db):

    user = db.get(User, 3)

    with pytest.raises(TicketNotFoundError):

        create_ticket_comment(
            db=db,
            ticket_id=2,
            comment_data=TicketCommentCreate(
                content="非法评论"
            ),
            current_user=user,
        )

    comments = db.scalars(
        select(TicketComment)
    ).all()

    assert comments == []


# ============================================
# 53. AGENT 不能评论未分配给自己的工单
# ============================================

def test_agent_cannot_comment_unassigned_ticket(db):

    agent = db.get(User, 2)

    with pytest.raises(TicketNotFoundError):

        create_ticket_comment(
            db=db,
            ticket_id=1,
            comment_data=TicketCommentCreate(
                content="非法评论"
            ),
            current_user=agent,
        )

    comments = db.scalars(
        select(TicketComment)
    ).all()

    assert comments == []


# ============================================
# 54. CLOSED 工单不能新增评论
# ============================================

def test_closed_ticket_rejects_comment(db):

    ticket = db.get(Ticket, 2)

    # ASSIGNED -> CLOSED
    ticket.status = "CLOSED"

    db.commit()

    admin = db.get(User, 1)

    with pytest.raises(TicketClosedForCommentError):

        create_ticket_comment(
            db=db,
            ticket_id=2,
            comment_data=TicketCommentCreate(
                content="关闭后不应该新增"
            ),
            current_user=admin,
        )

    comments = db.scalars(
        select(TicketComment)
    ).all()

    assert comments == []


# ============================================
# 55. 已逻辑删除的工单不能评论
# ============================================

def test_deleted_ticket_rejects_comment(db):

    admin = db.get(User, 1)

    with pytest.raises(TicketNotFoundError):

        create_ticket_comment(
            db=db,
            ticket_id=4,
            comment_data=TicketCommentCreate(
                content="不应该保存"
            ),
            current_user=admin,
        )

    comments = db.scalars(
        select(TicketComment)
    ).all()

    assert comments == []


# ============================================
# 56. 评论分页和排序测试
# ============================================

def test_ticket_comment_pagination(db):

    user = db.get(User, 3)
    admin = db.get(User, 1)

    # 创建三条评论
    contents = [
        "第一条评论",
        "第二条评论",
        "第三条评论",
    ]

    for content in contents:

        create_ticket_comment(
            db=db,
            ticket_id=1,
            comment_data=TicketCommentCreate(
                content=content
            ),
            current_user=user,
        )

    # 在另一张工单创建一条评论
    create_ticket_comment(
        db=db,
        ticket_id=3,
        comment_data=TicketCommentCreate(
            content="其他工单的评论"
        ),
        current_user=admin,
    )

    # 查询第一页
    page1, total = list_ticket_comments(
        db=db,
        current_user=admin,
        ticket_id=1,
        page=1,
        page_size=2,
    )

    # 查询第二页
    page2, total2 = list_ticket_comments(
        db=db,
        current_user=admin,
        ticket_id=1,
        page=2,
        page_size=2,
    )

    assert total == 3
    assert total2 == 3

    assert [
        item.content for item in page1
    ] == [
        "第一条评论",
        "第二条评论",
    ]

    assert [
        item.content for item in page2
    ] == [
        "第三条评论",
    ]


# ============================================
# 57. USER 不能查询别人的工单评论
# ============================================

def test_user_cannot_list_others_ticket_comments(db):

    user_a = db.get(User, 3)
    user_b = db.get(User, 4)

    create_ticket_comment(
        db=db,
        ticket_id=1,
        comment_data=TicketCommentCreate(
            content="用户甲的评论"
        ),
        current_user=user_a,
    )

    with pytest.raises(TicketNotFoundError):

        list_ticket_comments(
            db=db,
            current_user=user_b,
            ticket_id=1,
        )


# ============================================
# 58. AGENT 可以查询分配给自己的工单评论
# ============================================

def test_agent_can_list_assigned_ticket_comments(db):

    agent = db.get(User, 2)

    create_ticket_comment(
        db=db,
        ticket_id=2,
        comment_data=TicketCommentCreate(
            content="处理人员的进度说明"
        ),
        current_user=agent,
    )

    comments, total = list_ticket_comments(
        db=db,
        current_user=agent,
        ticket_id=2,
    )

    assert total == 1

    assert comments[0].content == "处理人员的进度说明"


# ============================================
# Ticket Comment HTTP 专项测试
# ============================================

def _build_comment_test_app(db, current_user):

    app = FastAPI()

    app.include_router(
        tickets_router,
        prefix="/api/v1",
    )

    app.dependency_overrides[get_db] = lambda: db

    app.dependency_overrides[get_current_user] = (
        lambda: current_user
    )

    return app


# ============================================
# 59. HTTP 创建评论成功
# ============================================

def test_http_ticket_comment_create_success(db):

    user = db.get(User, 3)

    app = _build_comment_test_app(db, user)

    try:

        with TestClient(app) as client:

            response = client.post(
                "/api/v1/tickets/1/comments",
                json={
                    "content": "网络问题仍然存在"
                },
            )

        assert response.status_code == 201

        body = response.json()

        assert body["ticket_id"] == 1
        assert body["user_id"] == 3
        assert body["content"] == "网络问题仍然存在"

        assert "password_hash" not in body

    finally:

        app.dependency_overrides.clear()


# ============================================
# 60. HTTP 无权评论返回 404
# ============================================

def test_http_ticket_comment_forbidden_user(db):

    user = db.get(User, 3)

    app = _build_comment_test_app(db, user)

    try:

        with TestClient(app) as client:

            response = client.post(
                "/api/v1/tickets/2/comments",
                json={
                    "content": "非法评论"
                },
            )

        assert response.status_code == 404

    finally:

        app.dependency_overrides.clear()


# ============================================
# 61. HTTP 已关闭工单返回 409
# ============================================

def test_http_ticket_comment_closed_ticket(db):

    ticket = db.get(Ticket, 2)

    ticket.status = "CLOSED"

    db.commit()

    admin = db.get(User, 1)

    app = _build_comment_test_app(db, admin)

    try:

        with TestClient(app) as client:

            response = client.post(
                "/api/v1/tickets/2/comments",
                json={
                    "content": "关闭后发表评论"
                },
            )

        assert response.status_code == 409

    finally:

        app.dependency_overrides.clear()


# ============================================
# 62. HTTP 查询评论分页
# ============================================

def test_http_ticket_comment_list_pagination(db):

    admin = db.get(User, 1)

    app = _build_comment_test_app(db, admin)

    try:

        with TestClient(app) as client:

            for content in [
                "第一条评论",
                "第二条评论",
            ]:

                response = client.post(
                    "/api/v1/tickets/1/comments",
                    json={
                        "content": content
                    },
                )

                assert response.status_code == 201

            response = client.get(
                "/api/v1/tickets/1/comments"
                "?page=1&page_size=1"
            )

        assert response.status_code == 200

        body = response.json()

        assert body["total"] == 2
        assert body["page"] == 1
        assert body["page_size"] == 1
        assert body["total_pages"] == 2
        assert len(body["items"]) == 1

    finally:

        app.dependency_overrides.clear()


# ============================================
# 63. HTTP 非法评论和分页参数
# ============================================

def test_http_ticket_comment_invalid_parameters(db):

    admin = db.get(User, 1)

    app = _build_comment_test_app(db, admin)

    try:

        with TestClient(app) as client:

            # 空白评论
            response1 = client.post(
                "/api/v1/tickets/1/comments",
                json={
                    "content": "   "
                },
            )

            # 非法分页
            response2 = client.get(
                "/api/v1/tickets/1/comments?page=0"
            )

        assert response1.status_code == 422
        assert response2.status_code == 422

    finally:

        app.dependency_overrides.clear()
