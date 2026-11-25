
from contextlib import nullcontext
from datetime import datetime as RealDateTime, timezone
from types import SimpleNamespace

import pytest

import app.services.ticket_service as service

from app.models.category import Category
from app.models.ticket import Ticket
from app.models.ticket_history import TicketHistory
from app.schemas.ticket import TicketCreate


# ============================================
# 1. 模拟数据库 Session
# ============================================

class FakeDB:

    def __init__(
        self,
        category_exists=True,
        latest_ticket_no=None,
        commit_error=None,
    ):

        self.category_exists = category_exists
        self.latest_ticket_no = latest_ticket_no
        self.commit_error = commit_error

        self.added = []

        self.commits = 0
        self.rollbacks = 0
        self.flushes = 0

        self.bind = SimpleNamespace(
            url=SimpleNamespace(
                database="flowdesk_test"
            )
        )

    def get_bind(self):
        return self.bind

    def get(self, model, pk):

        assert model is Category

        if self.category_exists:
            return SimpleNamespace(id=pk)

        return None

    def scalar(self, statement):
        return self.latest_ticket_no

    def add(self, obj):
        self.added.append(obj)

    def flush(self):

        self.flushes += 1

        for obj in self.added:

            if isinstance(obj, Ticket) and obj.id is None:
                obj.id = 101

    def refresh(self, obj):
        pass

    def commit(self):

        self.commits += 1

        if self.commit_error:
            raise self.commit_error

    def rollback(self):
        self.rollbacks += 1


# ============================================
# 2. 测试数据
# ============================================

def ticket_data():

    return TicketCreate(
        title="  Network down  ",
        description="  Cannot connect to office network  ",
        priority=" high ",
        category_id=10,
    )


class FixedDateTime:

    @classmethod
    def now(cls, tz=None):

        return RealDateTime(
            2026,
            11,
            23,
            tzinfo=timezone.utc,
        )


# ============================================
# 3. 编号生成测试
# ============================================

def test_first_number_of_day():

    db = FakeDB()

    result = service._next_ticket_number(
        db,
        "FD-20261123-",
    )

    assert result == "FD-20261123-00001"


def test_daily_number_increments():

    db = FakeDB(
        latest_ticket_no="FD-20261123-00042"
    )

    result = service._next_ticket_number(
        db,
        "FD-20261123-",
    )

    assert result == "FD-20261123-00043"


def test_daily_number_limit():

    db = FakeDB(
        latest_ticket_no="FD-20261123-99999"
    )

    with pytest.raises(
        service.TicketNumberExhaustedError
    ):

        service._next_ticket_number(
            db,
            "FD-20261123-",
        )


def test_malformed_existing_suffix():

    db = FakeDB(
        latest_ticket_no="FD-20261123-ABC"
    )

    with pytest.raises(
        service.TicketNumberGenerationError
    ):

        service._next_ticket_number(
            db,
            "FD-20261123-",
        )


# ============================================
# 4. 创建工单及历史记录测试
# ============================================

def test_create_ticket_and_history_commit_together(
    monkeypatch,
):

    monkeypatch.setattr(
        service,
        "_ticket_number_lock",
        lambda db, name: nullcontext(),
    )

    monkeypatch.setattr(
        service,
        "datetime",
        FixedDateTime,
    )

    db = FakeDB()

    user = SimpleNamespace(id=5)

    ticket = service.create_ticket(
        db,
        ticket_data(),
        user,
    )

    # 检查工单
    assert ticket.id == 101

    assert ticket.ticket_no == (
        "FD-20261123-00001"
    )

    assert ticket.title == "Network down"

    assert ticket.priority == "HIGH"

    assert ticket.status == "OPEN"

    assert ticket.creator_id == 5

    assert ticket.assignee_id is None

    assert ticket.category_id == 10

    # 检查事务
    assert db.commits == 1
    assert db.rollbacks == 0
    assert db.flushes == 2

    # 检查历史记录
    histories = [
        obj
        for obj in db.added
        if isinstance(obj, TicketHistory)
    ]

    assert len(histories) == 1

    history = histories[0]

    assert history.ticket_id == 101
    assert history.operator_id == 5

    assert history.action_type == "CREATE"
    assert history.field_name == "ticket"

    assert history.old_value is None

    assert history.new_value["ticket_no"] == (
        ticket.ticket_no
    )

    assert history.new_value["status"] == "OPEN"


# ============================================
# 5. 分类不存在测试
# ============================================

def test_missing_category_rolls_back(
    monkeypatch,
):

    monkeypatch.setattr(
        service,
        "_ticket_number_lock",
        lambda db, name: nullcontext(),
    )

    db = FakeDB(
        category_exists=False
    )

    with pytest.raises(
        service.CategoryNotFoundError
    ):

        service.create_ticket(
            db,
            ticket_data(),
            SimpleNamespace(id=5),
        )

    assert db.commits == 0
    assert db.rollbacks == 1
    assert db.added == []


# ============================================
# 6. 提交失败测试
# ============================================

def test_commit_failure_rolls_back(
    monkeypatch,
):

    monkeypatch.setattr(
        service,
        "_ticket_number_lock",
        lambda db, name: nullcontext(),
    )

    db = FakeDB(
        commit_error=RuntimeError(
            "commit failed"
        )
    )

    with pytest.raises(
        RuntimeError,
        match="commit failed",
    ):

        service.create_ticket(
            db,
            ticket_data(),
            SimpleNamespace(id=5),
        )

    assert db.commits == 1
    assert db.rollbacks == 1


# ============================================
# 7. 模拟 MySQL 命名锁连接
# ============================================

class FakeResult:

    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


class FakeConnection:

    def __init__(self, values):

        self.values = iter(values)

        self.calls = []

        self.closed = False
        self.invalidated = False

    def execute(self, statement, params):

        self.calls.append(
            (str(statement), params)
        )

        return FakeResult(
            next(self.values)
        )

    def invalidate(self):
        self.invalidated = True

    def close(self):
        self.closed = True


class FakeLockDB:

    def __init__(self, connection):

        self.connection = connection

    def get_bind(self):

        return SimpleNamespace(
            connect=lambda: self.connection
        )


# ============================================
# 8. 命名锁获取和释放测试
# ============================================

def test_named_lock_acquired_and_released():

    connection = FakeConnection([1, 1])

    db = FakeLockDB(connection)

    with service._ticket_number_lock(
        db,
        "flowdesk:test",
    ):

        assert not connection.closed

    assert len(connection.calls) == 2

    assert "GET_LOCK" in connection.calls[0][0]

    assert "RELEASE_LOCK" in connection.calls[1][0]

    assert connection.closed

    assert not connection.invalidated


# ============================================
# 9. 命名锁超时测试
# ============================================

def test_named_lock_timeout_closes_connection():

    connection = FakeConnection([0])

    db = FakeLockDB(connection)

    with pytest.raises(
        service.TicketNumberLockTimeoutError
    ):

        with service._ticket_number_lock(
            db,
            "flowdesk:test",
        ):

            pytest.fail(
                "Lock should not be acquired"
            )

    assert connection.closed

    assert len(connection.calls) == 1
