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


def test_init_db_heals_missing_segment_columns(app_settings):
    """旧 segments 表（缺 role/role_label/cleaned_content）经 init_db 自动补齐。"""
    engine = build_engine(app_settings)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE segments (
                id INTEGER NOT NULL PRIMARY KEY,
                session_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                seq INTEGER NOT NULL,
                speaker VARCHAR(1) NOT NULL,
                source VARCHAR(16) NOT NULL,
                content TEXT NOT NULL,
                start_ms INTEGER NOT NULL,
                end_ms INTEGER NOT NULL,
                confidence FLOAT
            )
            """
        )

    init_db(engine, app_settings)

    with engine.connect() as conn:
        columns = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(segments)")]

    for column in ("role", "role_label", "cleaned_content"):
        assert column in columns, f"segments 未补齐 {column}，实际列={columns}"


def test_init_db_heals_missing_job_columns(app_settings):
    """旧 jobs 表（缺 started_at/finished_at）经 init_db 自动补齐（T-S1.2）。"""
    engine = build_engine(app_settings)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE jobs (
                id INTEGER NOT NULL PRIMARY KEY,
                type VARCHAR(16) NOT NULL,
                session_id INTEGER NOT NULL,
                provider VARCHAR(64),
                status VARCHAR(16) NOT NULL,
                error TEXT
            )
            """
        )

    init_db(engine, app_settings)

    with engine.connect() as conn:
        columns = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(jobs)")]

    for column in ("started_at", "finished_at"):
        assert column in columns, f"jobs 未补齐 {column}，实际列={columns}"


def test_init_db_heals_missing_columns_in_old_schema(app_settings):
    """旧库（sessions 缺 cleaned_text）经 init_db 后自动补齐且原列/原数据完好。"""
    engine = build_engine(app_settings)
    old_columns = (
        "id",
        "user_id",
        "client_id",
        "mode",
        "status",
        "started_at",
        "duration_sec",
        "audio_path",
    )
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE sessions (
                id INTEGER NOT NULL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                client_id INTEGER,
                mode VARCHAR(16) NOT NULL,
                status VARCHAR(16) NOT NULL,
                started_at DATETIME NOT NULL,
                duration_sec INTEGER NOT NULL,
                audio_path VARCHAR(512)
            )
            """
        )
        conn.exec_driver_sql(
            "INSERT INTO sessions (id, user_id, mode, status, started_at, duration_sec) "
            "VALUES (7, 1, 'in_person', 'uploading', '2025-01-01 00:00:00', 0)"
        )

    init_db(engine, app_settings)

    with engine.connect() as conn:
        columns = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(sessions)")]
        rows = conn.exec_driver_sql(
            "SELECT id, user_id, duration_sec, cleaned_text, raw_transcript FROM sessions"
        ).all()

    assert "cleaned_text" in columns, f"sessions 未补齐 cleaned_text，实际列={columns}"
    assert "raw_transcript" in columns, f"sessions 未补齐 raw_transcript，实际列={columns}"
    for column in old_columns:
        assert column in columns, f"旧列 {column} 丢失，实际列={columns}"
    assert rows == [(7, 1, 0, None, None)], f"旧数据行受损: {rows}"

    # 幂等：再跑一次不报错、不重复加列
    init_db(engine, app_settings)
    with engine.connect() as conn:
        columns_after = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(sessions)")]
    assert columns_after == columns
