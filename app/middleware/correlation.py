"""Middleware for Request and Correlation ID propagation."""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.correlation import sanitize_request_id, set_request_id


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Ensures every incoming request has an assigned correlation ID."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        client_request_id = request.headers.get("X-Request-ID")
        request_id = sanitize_request_id(client_request_id)

        # Store in contextvar for structlog and downstream services
        set_request_id(request_id)
        # Store in request state for endpoint handlers
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
