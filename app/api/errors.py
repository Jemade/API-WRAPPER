"""Global exception handlers mapping errors to standardized JSON responses."""

import sys
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.correlation import get_request_id
from app.core.exceptions import GatewayException
from app.core.logging import get_logger

logger = get_logger("api.errors")


def register_error_handlers(app: FastAPI) -> None:
    """Register centralized exception handlers for the FastAPI application."""

    @app.exception_handler(GatewayException)
    async def gateway_exception_handler(_request: Request, exc: GatewayException) -> JSONResponse:
        request_id = get_request_id()
        content: dict[str, Any] = {
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": request_id,
            }
        }
        if exc.details:
            content["error"]["details"] = exc.details

        headers = {}
        if hasattr(exc, "retry_after") and exc.retry_after is not None:
            headers["Retry-After"] = str(exc.retry_after)

        return JSONResponse(status_code=exc.status_code, content=content, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = get_request_id()
        logger.warning(
            "Request validation failed",
            request_id=request_id,
            errors=exc.errors(),
        )
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "Request validation failed.",
                    "request_id": request_id,
                    "details": {"validation_errors": exc.errors()},
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        request_id = get_request_id()
        code_map = {
            401: "UNAUTHORIZED",
            403: "UNAUTHORIZED",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            429: "RATE_LIMITED",
        }
        code = code_map.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": code,
                    "message": exc.detail or "An HTTP error occurred.",
                    "request_id": request_id,
                }
            },
            headers=exc.headers or {},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
        request_id = get_request_id()
        logger.error(
            "Unhandled server exception",
            request_id=request_id,
            exc_info=sys.exc_info(),
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected internal error occurred. Please contact support.",
                    "request_id": request_id,
                }
            },
        )
