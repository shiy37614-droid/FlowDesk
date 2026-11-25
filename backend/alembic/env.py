
from logging.config import fileConfig

from alembic import context

from app.db.base import Base
from app.db.session import engine

# 导入全部 ORM 模型，确保注册到 Base.metadata
import app.models  # noqa: F401


# ============================================
# 1. Alembic Configuration
# ============================================

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# ============================================
# 2. ORM Metadata
# ============================================

target_metadata = Base.metadata


# ============================================
# 3. 防止误识别未知数据库表
# ============================================

def include_name(name, type_, parent_names):

    if type_ == "table":

        return name in target_metadata.tables

    return True


# ============================================
# 4. Offline Migration
# ============================================

def run_migrations_offline() -> None:
    """
    不建立数据库连接，生成 SQL 迁移语句。
    """

    context.configure(
        url=engine.url,
        target_metadata=target_metadata,

        literal_binds=True,

        dialect_opts={
            "paramstyle": "named",
        },

        compare_type=True,
        compare_server_default=False,

        include_name=include_name,
    )

    with context.begin_transaction():

        context.run_migrations()


# ============================================
# 5. Online Migration
# ============================================

def run_migrations_online() -> None:
    """
    使用 FlowDesk 已有的 SQLAlchemy Engine
    执行数据库迁移。
    """

    with engine.connect() as connection:

        context.configure(
            connection=connection,
            target_metadata=target_metadata,

            compare_type=True,
            compare_server_default=False,

            include_name=include_name,
        )

        with context.begin_transaction():

            context.run_migrations()


# ============================================
# 6. Migration Entry Point
# ============================================

if context.is_offline_mode():

    run_migrations_offline()

else:

    run_migrations_online()
