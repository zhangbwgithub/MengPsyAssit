"""FastAPI 应用工厂与模块级 app。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import Settings, get_settings
from .db import build_engine, create_session_factory, init_db
from .logging_conf import setup_logging
from .response import register_exception_handlers
from .routes import router as sessions_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """应用工厂：可注入自定义 Settings（测试用临时 SQLite）。"""
    app_settings = settings if settings is not None else get_settings()
    setup_logging()
    engine = build_engine(app_settings)
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # startup：建表 + dev 模式播种默认用户
        init_db(engine, app_settings)
        yield

    application = FastAPI(title="psy-backend", lifespan=lifespan)
    application.state.settings = app_settings
    application.state.engine = engine
    application.state.session_factory = session_factory

    register_exception_handlers(application)
    application.include_router(sessions_router)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "app": "psy-backend", "env": app_settings.app_env}

    return application


app = create_app()
