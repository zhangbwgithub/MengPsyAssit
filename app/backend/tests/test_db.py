"""init_db：7 张表齐全 + user_id 隔离列 + dev 播种。"""

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from psyapp.db import build_engine, init_db
from psyapp.models import User

EXPECTED_TABLES = {"users", "clients", "sessions", "segments", "records", "themes", "jobs"}
USER_ID_TABLES = ("clients", "sessions", "segments", "records")


def test_init_db_creates_all_tables_with_user_id(app_settings):
    engine = build_engine(app_settings)
    init_db(engine, app_settings)

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    assert EXPECTED_TABLES <= table_names

    for table in USER_ID_TABLES:
        columns = {col["name"] for col in inspector.get_columns(table)}
        assert "user_id" in columns, f"{table} 缺少 user_id 列"


def test_init_db_seeds_dev_user_in_dev(app_settings):
    engine = build_engine(app_settings)
    init_db(engine, app_settings)

    with Session(engine) as session:
        user = session.get(User, app_settings.dev_user_id)
        assert user is not None
        assert user.username == "dev"

    # 幂等：再次执行不报错、不重复播种
    init_db(engine, app_settings)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(User)) == 1
