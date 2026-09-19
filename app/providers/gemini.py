"""Google Gemini provider adapter."""

from typing import Any

import httpx

from app.core.exceptions import ProviderConfigurationError
from app.core.logging import get_logger
from app.providers.base import LLMProvider
from app.schemas.generate import ChatRequest
from app.schemas.response import LLMResponse

logger = get_logger("providers.gemini")


class GeminiProvider(LLMProvider):
    """Adapter for Google Gemini generateContent API."""

    provider_name: str = "gemini"

    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        settings: Any | None = None,
    ) -> None:
        super().__init__(http_client=http_client, settings=settings)

    async def _call_provider(self, request: ChatRequest, request_id: str) -> LLMResponse:
        api_key = self.settings.gemini_api_key
        if not api_key:
            raise ProviderConfigurationError("Gemini API key is not configured.")

        model_name = request.model.strip()
        if model_name == "gemini":
            model_name = "gemini-3.6-flash"
        if model_name.startswith("models/"):
            model_name = model_name[len("models/") :]

        url = f"{self.settings.gemini_api_base.rstrip('/')}/models/{model_name}:generateContent"
        headers = {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
            "User-Agent": "Production-LLM-Gateway/0.1.0",
        }

        system_instruction: dict[str, Any] | None = None
        contents: list[dict[str, Any]] = []

        for m in request.messages:
            if m.role == "system":
                system_instruction = {"parts": [{"text": m.content}]}
            elif m.role == "assistant":
                contents.append({"role": "model", "parts": [{"text": m.content}]})
            else:
                contents.append({"role": "user", "parts": [{"text": m.content}]})

        generation_config: dict[str, Any] = {}
        if request.temperature is not None:
            generation_config["temperature"] = request.temperature
        if request.max_tokens is not None:
            generation_config["maxOutputTokens"] = request.max_tokens

        payload: dict[str, Any] = {"contents": contents}
        if system_instruction is not None:
            payload["systemInstruction"] = system_instruction
        if generation_config:
            payload["generationConfig"] = generation_config

        client = await self.get_client()
        response = await client.post(url, json=payload, headers=headers)

        if response.status_code != 200:
            self._handle_http_error(response.status_code, response.text, request_id)

        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            content = ""
            finish_reason = "stop"
        else:
            first_candidate = candidates[0]
            content_obj = first_candidate.get("content", {})
            parts = content_obj.get("parts", [])
            content = "".join(
                part.get("text", "") for part in parts if isinstance(part, dict) and "text" in part
            )
            raw_finish = first_candidate.get("finishReason", "STOP")
            if raw_finish in ("STOP", None):
                finish_reason = "stop"
            elif raw_finish == "MAX_TOKENS":
                finish_reason = "length"
            elif raw_finish in ("SAFETY", "RECITATION"):
                finish_reason = "content_filter"
            else:
                finish_reason = str(raw_finish).lower()

        usage = data.get("usageMetadata", {})
        input_tokens = int(usage.get("promptTokenCount", 0))
        output_tokens = int(usage.get("candidatesTokenCount", 0))
        total_tokens = int(usage.get("totalTokenCount", input_tokens + output_tokens))

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
