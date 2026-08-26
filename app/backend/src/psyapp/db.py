"""SQLAlchemy 2.0 engine/session 与 init_db（create_all + dev 播种 + SQLite 列补齐）。

dev 期 SQLite 列补齐策略：`Base.metadata.create_all()` 只建新表、不会 ALTER
已存在的旧表。为避免每次增量加列都要手工删库，init_db 在 create_all 之后对
SQLite 做轻量 `ALTER TABLE ... ADD COLUMN`（幂等）。正式迁移工具（alembic）
留待需要时再引入——这不是 alembic，任务卡禁 alembic 的约束不违反。
"""

from __future__ import annotations

import logging

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings
from .models import Base, User

logger = logging.getLogger(__name__)


def _heal_missing_columns(engine: Engine) -> list[str]:
    """SQLite 专用：把 metadata 中新增、但旧表缺失的列用 ALTER TABLE 补上。

    只做加法（新列 nullable、不带 default），不动已有列、不删列、不改类型；
    无缺失列时零 DDL 操作。返回本次补齐的列清单（`表名.列名 (类型)`），供日志记录。
    """
    if engine.dialect.name != "sqlite":
        return []

    added: list[str] = []
    with engine.begin() as conn:
        preparer = conn.dialect.identifier_preparer
        for table in Base.metadata.tables.values():
            table_name = table.name
            actual = {
                row[1]
                for row in conn.exec_driver_sql(
                    f"PRAGMA table_info({preparer.quote(table_name)})"
                )
            }
            for column in table.columns:
                if column.name in actual:
                    continue
                col_type = column.type.compile(dialect=conn.dialect)
                ddl = (
                    f"ALTER TABLE {preparer.quote(table_name)} "
                    f"ADD COLUMN {preparer.quote(column.name)} {col_type}"
                )
                conn.exec_driver_sql(ddl)
                added.append(f"{table_name}.{column.name} ({col_type})")

    return added


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
    """建表 + SQLite 旧表列补齐 + dev 模式播种默认用户（幂等）。"""
    Base.metadata.create_all(engine)
    healed = _heal_missing_columns(engine)
    if healed:
        logger.info("schema 列补齐（dev SQLite ALTER TABLE 加法）: %s", ", ".join(healed))
    if settings.app_env != "dev":
        return
    with Session(engine) as session:
        has_users = session.scalar(select(User.id).limit(1)) is not None
        if not has_users:
            session.add(
                User(id=settings.dev_user_id, username="dev", password_hash="")
            )
            session.commit()
