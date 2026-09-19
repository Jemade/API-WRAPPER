"""Anthropic provider adapter."""

from typing import Any

import httpx

from app.core.exceptions import ProviderConfigurationError
from app.core.logging import get_logger
from app.providers.base import LLMProvider
from app.schemas.generate import ChatRequest
from app.schemas.response import LLMResponse

logger = get_logger("providers.anthropic")


class AnthropicProvider(LLMProvider):
    """Adapter for Anthropic Messages API."""

    provider_name: str = "anthropic"

    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        settings: Any | None = None,
    ) -> None:
        super().__init__(http_client=http_client, settings=settings)

    async def _call_provider(self, request: ChatRequest, request_id: str) -> LLMResponse:
        api_key = self.settings.anthropic_api_key
        if not api_key:
            raise ProviderConfigurationError("Anthropic API key is not configured.")

        url = f"{self.settings.anthropic_api_base.rstrip('/')}/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
            "User-Agent": "Production-LLM-Gateway/0.1.0",
        }

        # Anthropic separates system prompts from message history
        system_prompts: list[str] = []
        anthropic_messages: list[dict[str, str]] = []

        for m in request.messages:
            if m.role == "system":
                system_prompts.append(m.content)
            else:
                anthropic_messages.append({"role": m.role, "content": m.content})

        payload: dict[str, Any] = {
            "model": request.model,
            "messages": anthropic_messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if system_prompts:
            payload["system"] = "\n\n".join(system_prompts)

        client = await self.get_client()
        response = await client.post(url, json=payload, headers=headers)

        if response.status_code != 200:
            self._handle_http_error(response.status_code, response.text, request_id)

        data = response.json()
        content_blocks = data.get("content", [])
        content = "".join(
            block.get("text", "") for block in content_blocks if block.get("type") == "text"
        )
        finish_reason = data.get("stop_reason") or "end_turn"

        usage = data.get("usage", {})
        input_tokens = int(usage.get("input_tokens", 0))
        output_tokens = int(usage.get("output_tokens", 0))
        total_tokens = input_tokens + output_tokens

        return LLMResponse(
            request_id=request_id,
            provider=self.provider_name,
            model=request.model,
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            finish_reason=finish_reason,
            latency_ms=0.0,
        )
