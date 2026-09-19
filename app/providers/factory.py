"""Provider factory and model routing."""

import httpx

from app.core.exceptions import InvalidRequestError
from app.providers.anthropic import AnthropicProvider
from app.providers.base import LLMProvider
from app.providers.gemini import GeminiProvider
from app.providers.openai import OpenAIProvider


class ProviderFactory:
    """Resolves and instantiates the appropriate LLM provider adapter based on model name."""

    _GEMINI_PREFIXES = ("gemini-", "gemma-")
    _OPENAI_PREFIXES = ("gpt-", "o1-", "o3-", "chatgpt-", "text-embedding-")
    _ANTHROPIC_PREFIXES = ("claude-",)

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._http_client = http_client
        self._providers: dict[str, LLMProvider] = {
            "gemini": GeminiProvider(http_client=self._http_client),
            "openai": OpenAIProvider(http_client=self._http_client),
            "anthropic": AnthropicProvider(http_client=self._http_client),
        }

    def resolve(self, model: str) -> LLMProvider:
        """Inspect model identifier and return the corresponding provider adapter."""
        normalized_model = model.lower().strip()

        if normalized_model in ("gemini", "default") or any(
            normalized_model.startswith(prefix) for prefix in self._GEMINI_PREFIXES
        ):
            return self._providers["gemini"]

        if any(normalized_model.startswith(prefix) for prefix in self._OPENAI_PREFIXES):
            return self._providers["openai"]

        if any(normalized_model.startswith(prefix) for prefix in self._ANTHROPIC_PREFIXES):
            return self._providers["anthropic"]

        raise InvalidRequestError(
            f"Unsupported model '{model}'. Supported prefixes: "
            f"{list(self._GEMINI_PREFIXES + self._OPENAI_PREFIXES + self._ANTHROPIC_PREFIXES)}."
        )

    def get_provider(self, name: str) -> LLMProvider:
        """Directly retrieve a provider by name."""
        if name in self._providers:
            return self._providers[name]
        raise InvalidRequestError(f"Unknown provider '{name}'.")
