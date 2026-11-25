
from sqlalchemy.orm import DeclarativeBase


# ============================================
# FlowDesk ORM Base
# ============================================

class Base(DeclarativeBase):
    """
    FlowDesk 所有 ORM 模型的统一基类。

    所有数据库模型都应该继承这个 Base。
    """

    pass
