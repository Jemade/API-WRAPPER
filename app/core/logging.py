"""Structured JSON logging configuration using structlog."""

import logging
import sys
from typing import Any, cast

import structlog
from structlog.types import EventDict, WrappedLogger

from app.core.correlation import CORRELATION_ID_CTX

# Sensitive keys to redact from logs
SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "x-api-key",
    "openai_api_key",
    "anthropic_api_key",
    "webhook_secret",
    "password",
    "secret",
    "token",
}


def redact_sensitive_data(
    _logger: WrappedLogger,
    _name: str,
    event_dict: EventDict,
) -> EventDict:
    """Redact sensitive credentials and header values from structured log events."""
    for key, val in list(event_dict.items()):
        if any(s in key.lower() for s in SENSITIVE_KEYS):
            event_dict[key] = "[REDACTED]"
        elif isinstance(val, dict):
            event_dict[key] = redact_dict(val)
    return event_dict


def redact_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively redact sensitive keys in nested dictionaries."""
    sanitized: dict[str, Any] = {}
    for k, v in data.items():
        if any(s in k.lower() for s in SENSITIVE_KEYS):
            sanitized[k] = "[REDACTED]"
        elif isinstance(v, dict):
            sanitized[k] = redact_dict(v)
        else:
            sanitized[k] = v
    return sanitized


def add_correlation_id(
    _logger: WrappedLogger,
    _name: str,
    event_dict: EventDict,
) -> EventDict:
    """Inject current correlation ID from contextvar into all log records."""
    req_id = CORRELATION_ID_CTX.get()
    if req_id and "request_id" not in event_dict:
        event_dict["request_id"] = req_id
    return event_dict


def configure_logging(log_level: str = "INFO", is_dev: bool = False) -> None:
    """Configure structlog and standard logging."""
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        add_correlation_id,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        redact_sensitive_data,
    ]

    renderer: structlog.types.Processor
    if is_dev:
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level.upper())

    # Quiet noisy third-party loggers
    for noisy in ("uvicorn.access", "httpcore", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a bound structlog logger."""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name or "gateway"))
