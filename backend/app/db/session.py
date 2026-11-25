
from collections.abc import Generator

from sqlalchemy import URL, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


# ============================================
# 1. 创建数据库连接 URL
# ============================================

DATABASE_URL = URL.create(
    drivername="mysql+pymysql",
    username=settings.mysql_user,
    password=settings.mysql_password.get_secret_value(),
    host=settings.mysql_host,
    port=settings.mysql_port,
    database=settings.mysql_database,
    query={
        "charset": settings.mysql_charset,
    },
)


# ============================================
# 2. 创建 Engine
# ============================================

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    echo=False,
    connect_args={
        "init_command": "SET time_zone = '+00:00'",
    },
)


# ============================================
# 3. 创建 Session 工厂
# ============================================

SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    expire_on_commit=False,
)


# ============================================
# 4. FastAPI 数据库依赖
# ============================================

def get_db() -> Generator[Session, None, None]:
    """
    为一次 API 请求提供独立的数据库 Session。

    请求结束后自动关闭 Session。
    """

    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()
