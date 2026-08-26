"""统一日志配置：时间/级别/模块格式，stdout 输出，并过滤 api key 明文。"""

from __future__ import annotations

import logging
import re
import sys

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# sk- 开头的密钥形态（含 dashscope/各大厂商常见形态），日志侧兜底掩码
_SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-]{4,}")


class SecretRedactFilter(logging.Filter):
    """把日志记录中的密钥明文替换为 sk-***。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _SECRET_PATTERN.sub("sk-***", record.msg)
        if record.args:
            redacted = []
            for arg in record.args:
                if isinstance(arg, str):
                    redacted.append(_SECRET_PATTERN.sub("sk-***", arg))
                else:
                    redacted.append(arg)
            record.args = tuple(redacted)
        return True


def _add_filters_to_existing_handlers() -> None:
    """给 uvicorn 等库在启动后自建的 handler 补装掩码过滤器（幂等）。"""
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.addFilter(SecretRedactFilter())
        for handler in logger.handlers:
            if not any(isinstance(f, SecretRedactFilter) for f in handler.filters):
                handler.addFilter(SecretRedactFilter())


def setup_logging(level: int = logging.INFO) -> None:
    """配置根 logger：stdout 输出 + 统一格式 + 密钥掩码。可重复调用。"""
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    handler.addFilter(SecretRedactFilter())
    root.addHandler(handler)
    root.setLevel(level)
    _add_filters_to_existing_handlers()
