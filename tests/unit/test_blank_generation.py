import pytest
from pydantic import ValidationError

from app.schemas.generate import ChatMessage, ChatRequest


@pytest.mark.parametrize("blank", [" ", "\t\n"])
def test_blank_model_is_rejected(blank):
    with pytest.raises(ValidationError):
        ChatRequest(model=blank, messages=[ChatMessage(role="user", content="hi")])


@pytest.mark.parametrize("blank", [" ", "\t\n"])
def test_blank_message_is_rejected(blank):
    with pytest.raises(ValidationError):
        ChatMessage(role="user", content=blank)


def test_model_trim_preserves_message_formatting():
    content = "  def solve():\n    return 1\n"
    request = ChatRequest(model=" gpt-4o ", messages=[ChatMessage(role="user", content=content)])
    assert request.model == "gpt-4o"
    assert request.messages[0].content == content
