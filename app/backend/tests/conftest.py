"""pytest fixtures：临时 SQLite + TestClient。"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from psyapp.config import Settings
from psyapp.main import create_app


@pytest.fixture()
def app_settings(tmp_path) -> Settings:
    """每个测试独立的临时 SQLite 配置。"""
    return Settings(
        app_env="dev",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        data_dir=str(tmp_path),
        dev_user_id=1,
        dashscope_api_key="",
    )


@pytest.fixture()
def client(app_settings) -> Iterator[TestClient]:
    """基于临时配置创建应用并触发 lifespan（init_db）。"""
    app = create_app(app_settings)
    with TestClient(app) as test_client:
        yield test_client
