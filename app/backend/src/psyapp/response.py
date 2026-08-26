"""统一响应封装与全局异常处理。"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

_HTTP_CODES = {
    404: "not_found",
    405: "method_not_allowed",
}


class ApiError(Exception):
    """业务异常：code + message + http_status。"""

    def __init__(self, code: str, message: str, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def ok(data: Any = None) -> dict[str, Any]:
    """成功响应体。"""
    return {"ok": True, "data": data}


def error(code: str, message: str) -> dict[str, Any]:
    """失败响应体。"""
    return {"ok": False, "error": {"code": code, "message": message}}


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器：ApiError / 参数校验 / HTTP 404 等 / 未知 500。"""

    @app.exception_handler(ApiError)
    async def handle_api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=error(exc.code, exc.message),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, _exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error("validation_error", "请求参数校验失败"),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "http_error")
        return JSONResponse(
            status_code=exc.status_code,
            content=error(code, str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, _exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=error("internal_error", "服务器内部错误"),
        )
