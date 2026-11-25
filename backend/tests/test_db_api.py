
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.session import get_db
from app.main import app


client = TestClient(app)


# ============================================
# 1. 测试真实 MySQL 数据库连接
# ============================================

def test_database_health_endpoint():

    response = client.get("/health/db")

    assert response.status_code == 200

    assert response.json() == {
        "status": "ok",
        "database": settings.mysql_database,
        "timezone": "+00:00",
    }


# ============================================
# 2. 测试数据库异常处理
# ============================================

def test_database_health_returns_503_when_database_fails(
    monkeypatch,
):

    class BrokenSession:

        def execute(self, statement):
            raise SQLAlchemyError("Simulated database failure")

    def override_get_db():
        yield BrokenSession()

    # 临时替换数据库依赖
    monkeypatch.setitem(
        app.dependency_overrides,
        get_db,
        override_get_db,
    )

    response = client.get("/health/db")

    assert response.status_code == 503

    assert response.json() == {
        "detail": "Database unavailable"
    }
