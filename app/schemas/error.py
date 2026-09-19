"""Standardized error schemas returned across all endpoints."""

from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Structured error payload details."""

    code: str = Field(
        ...,
        description="Standardized error code (e.g. 'RATE_LIMITED', 'INVALID_REQUEST').",
        examples=["RATE_LIMITED", "UPSTREAM_TIMEOUT", "INVALID_REQUEST"],
    )
    message: str = Field(
        ...,
        description="Human-readable explanation of the error.",
    )
    request_id: str = Field(
        ...,
        description="Correlation ID associated with the failed request.",
    )
    details: dict[str, Any] | None = Field(
        default=None,
        description="Optional additional error context (omitted in production if empty).",
    )


class ErrorResponse(BaseModel):
    """Top-level error response envelope."""

    error: ErrorDetail
