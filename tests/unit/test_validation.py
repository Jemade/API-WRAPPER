"""Unit tests for Pydantic request validation."""

import pytest
from pydantic import ValidationError

from app.schemas.generate import ChatMessage, ChatRequest


def test_valid_chat_request() -> None:
    """A valid ChatRequest model instantiates successfully."""
    req = ChatRequest(
        model="gpt-4o",
        messages=[
            ChatMessage(role="system", content="You are a helpful assistant."),
            ChatMessage(role="user", content="Hello world!"),
        ],
        temperature=0.7,
        max_tokens=500,
        webhook_url="https://example.com/webhook",
    )
    assert req.model == "gpt-4o"
    assert len(req.messages) == 2
    assert req.temperature == 0.7
    assert req.max_tokens == 500
    assert str(req.webhook_url) == "https://example.com/webhook"


def test_empty_messages_rejected() -> None:
    """An empty messages list is rejected."""
    with pytest.raises(ValidationError) as exc_info:
        ChatRequest(model="gpt-4o", messages=[])
    assert "messages" in str(exc_info.value)


def test_invalid_role_rejected() -> None:
    """An unsupported message role is rejected."""
    with pytest.raises(ValidationError) as exc_info:
        ChatMessage(role="moderator", content="Hello")  # type: ignore[arg-type]
    assert "role" in str(exc_info.value)


def test_empty_content_rejected() -> None:
    """Empty string content is rejected."""
    with pytest.raises(ValidationError) as exc_info:
        ChatMessage(role="user", content="")
    assert "content" in str(exc_info.value)


def test_invalid_temperature_range() -> None:
    """Temperature must be within [0.0, 2.0]."""
    with pytest.raises(ValidationError):
        ChatRequest(
            model="gpt-4o",
            messages=[ChatMessage(role="user", content="hi")],
            temperature=-0.1,
        )

    with pytest.raises(ValidationError):
        ChatRequest(
            model="gpt-4o",
            messages=[ChatMessage(role="user", content="hi")],
            temperature=2.5,
        )


def test_invalid_max_tokens() -> None:
    """max_tokens must be greater than 0 and within 32000."""
    with pytest.raises(ValidationError):
        ChatRequest(
            model="gpt-4o",
            messages=[ChatMessage(role="user", content="hi")],
            max_tokens=0,
        )

    with pytest.raises(ValidationError):
        ChatRequest(
            model="gpt-4o",
            messages=[ChatMessage(role="user", content="hi")],
            max_tokens=100000,
        )


def test_invalid_webhook_url() -> None:
    """Malformed webhook URLs are rejected."""
    with pytest.raises(ValidationError):
        ChatRequest(
            model="gpt-4o",
            messages=[ChatMessage(role="user", content="hi")],
            webhook_url="not-a-valid-url",  # type: ignore[arg-type]
        )
