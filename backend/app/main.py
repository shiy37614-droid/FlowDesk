
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.auth import router as auth_router
from app.db.session import get_db

from app.api.v1.tickets import router as tickets_router
from app.api.v1.attachments import router as attachments_router
# ============================================
# FlowDesk FastAPI Application
# ============================================

app = FastAPI(
    title="FlowDesk API",
    description="FlowDesk 工单管理系统后端 API",
    version="0.1.0",
)


# ============================================
# 注册 API Router
# ============================================

app.include_router(
    auth_router,
    prefix="/api/v1",
)

app.include_router(
    tickets_router,
    prefix="/api/v1",
)

app.include_router(
    attachments_router,
    prefix="/api/v1",
)
# ============================================
# 1. Health Check
# ============================================

@app.get(
    "/health",
    tags=["Health"],
    summary="健康检查",
)
def health_check() -> dict[str, str]:

    return {
        "status": "ok",
        "service": "FlowDesk API",
        "version": "0.1.0",
    }


# ============================================
# 2. Database Health Check
# ============================================

@app.get(
    "/health/db",
    tags=["Health"],
    summary="数据库连接检查",
)
def database_health_check(
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:

    try:
        db.execute(
            text("SELECT 1")
        ).scalar_one()

        database = db.execute(
            text("SELECT DATABASE()")
        ).scalar_one()

        timezone = db.execute(
            text("SELECT @@session.time_zone")
        ).scalar_one()

    except SQLAlchemyError as exc:

        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from exc

    return {
        "status": "ok",
        "database": database,
        "timezone": timezone,
    }
