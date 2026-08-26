"""SQLAlchemy 2.0 engine/session 与 init_db（create_all + dev 播种）。"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings
from .models import Base, User


def build_engine(settings: Settings) -> Engine:
    """按配置创建 engine；SQLite 关闭同线程检查（FastAPI 线程池共用）。"""
    connect_args = {}
    if settings.database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    return create_engine(settings.database_url, connect_args=connect_args)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """创建 sessionmaker（S0 同步用法，不引入 aiosqlite）。"""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(engine: Engine, settings: Settings) -> None:
    """建表 + dev 模式播种默认用户（users 为空且 idempotent）。"""
    Base.metadata.create_all(engine)
    if settings.app_env != "dev":
        return
    with Session(engine) as session:
        has_users = session.scalar(select(User.id).limit(1)) is not None
        if not has_users:
            session.add(
                User(id=settings.dev_user_id, username="dev", password_hash="")
            )
            session.commit()
