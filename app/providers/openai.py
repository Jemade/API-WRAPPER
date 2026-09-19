"""OpenAI provider adapter."""

from typing import Any

import httpx

from app.core.exceptions import ProviderConfigurationError
from app.core.logging import get_logger
from app.providers.base import LLMProvider
from app.schemas.generate import ChatRequest
from app.schemas.response import LLMResponse

logger = get_logger("providers.openai")


class OpenAIProvider(LLMProvider):
    """Adapter for OpenAI Chat Completions API."""

    provider_name: str = "openai"

    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        settings: Any | None = None,
    ) -> None:
        super().__init__(http_client=http_client, settings=settings)

    async def _call_provider(self, request: ChatRequest, request_id: str) -> LLMResponse:
        api_key = self.settings.openai_api_key
        if not api_key:
            raise ProviderConfigurationError("OpenAI API key is not configured.")

        url = f"{self.settings.openai_api_base.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Production-LLM-Gateway/0.1.0",
        }

        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        client = await self.get_client()
        response = await client.post(url, json=payload, headers=headers)

        if response.status_code != 200:
            self._handle_http_error(response.status_code, response.text, request_id)

        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            content = ""
            finish_reason = "stop"
        else:
            first_choice = choices[0]
            content = first_choice.get("message", {}).get("content", "") or ""
            finish_reason = first_choice.get("finish_reason", "stop") or "stop"

        usage = data.get("usage", {})
        input_tokens = int(usage.get("prompt_tokens", 0))
        output_tokens = int(usage.get("completion_tokens", 0))
        total_tokens = int(usage.get("total_tokens", input_tokens + output_tokens))

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
