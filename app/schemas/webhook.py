"""Schemas for webhook events and payloads."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class WebhookEvent(BaseModel):
    """Event envelope delivered to client webhook endpoints."""

    event_id: str = Field(..., description="Unique ID for this webhook delivery event.")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp of event creation.")
    request_id: str = Field(
        ..., description="Correlation ID of the originating generation request."
    )
    event_type: Literal["generation.completed", "generation.failed"] = Field(
        ...,
        description="Type of event delivered.",
    )
    payload: dict[str, Any] = Field(
        ...,
        description="Event payload (normalized LLMResponse or ErrorDetail).",
    )
