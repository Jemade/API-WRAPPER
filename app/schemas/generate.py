"""Request schemas for LLM generation."""

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class ChatMessage(BaseModel):
    """A single chat message in the conversation history."""

    role: Literal["system", "user", "assistant"] = Field(
        ...,
        description="Role of the message author.",
    )
    content: str = Field(
        ...,
        min_length=1,
        description="The content of the message.",
    )


class ChatRequest(BaseModel):
    """Normalized generation request payload."""

    model: str = Field(
        ...,
        min_length=1,
        description="Target model identifier (e.g. 'gpt-4o', 'claude-3-5-sonnet-20241022').",
        examples=["gpt-4o", "claude-3-5-sonnet-20241022"],
    )
    messages: list[ChatMessage] = Field(
        ...,
        min_length=1,
        description="Non-empty list of conversation messages.",
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Sampling temperature between 0.0 and 2.0.",
    )
    max_tokens: int = Field(
        default=1000,
        gt=0,
        le=32000,
        description="Maximum number of tokens to generate.",
    )
    webhook_url: HttpUrl | None = Field(
        default=None,
        description="Optional webhook URL to receive an HMAC-signed event upon completion.",
    )
