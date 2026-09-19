"""Middleware for structured HTTP request/response logging and latency profiling."""

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.correlation import get_request_id
from app.core.logging import get_logger

logger = get_logger("middleware.logging")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs incoming HTTP requests with status codes and measured latency."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start_time = time.perf_counter()
        request_id = get_request_id()

        try:
            response = await call_next(request)
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

            # Skip noisy health check logging in production
            if request.url.path not in ("/health", "/ready"):
                logger.info(
                    "HTTP request completed",
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    latency_ms=latency_ms,
                    request_id=request_id,
                )
            return response

        except Exception as exc:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(
                "Unhandled error during HTTP request",
                method=request.method,
                path=request.url.path,
                latency_ms=latency_ms,
                request_id=request_id,
                error=str(exc),
            )
            raise
