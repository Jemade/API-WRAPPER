"""Correlation and Request ID tracking using contextvars."""

import re
import uuid
from contextvars import ContextVar

CORRELATION_ID_CTX: ContextVar[str] = ContextVar("correlation_id", default="")

# Allowed characters for client-supplied correlation IDs: alphanumeric, dash, underscore
_REQUEST_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")


def generate_request_id() -> str:
    """Generate a unique request ID with a 'req_' prefix."""
    return f"req_{uuid.uuid4().hex}"


def sanitize_request_id(client_id: str | None) -> str:
    """Validate and sanitize a client-provided request ID or generate a new one.

    If the client supplies an acceptable format (alphanumeric, dashes, underscores, max 64 chars),
    we preserve it to facilitate end-to-end tracing across caller systems.
    Otherwise, we generate a fresh UUID-based request ID.
    """
    if client_id and _REQUEST_ID_PATTERN.match(client_id.strip()):
        return client_id.strip()
    return generate_request_id()


def get_request_id() -> str:
    """Retrieve the current request ID from the contextvar."""
    req_id = CORRELATION_ID_CTX.get()
    return req_id if req_id else "unknown_req"


def set_request_id(request_id: str) -> None:
    """Set the current request ID in the contextvar."""
    CORRELATION_ID_CTX.set(request_id)
