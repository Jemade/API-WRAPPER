"""Abstract base class for LLM provider adapters."""

import time
from abc import ABC, abstractmethod

import httpx
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    GatewayException,
    ProviderConfigurationError,
    UpstreamBadRequestError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)
from app.core.logging import get_logger
from app.schemas.generate import ChatRequest
from app.schemas.response import LLMResponse

logger = get_logger("providers.base")


class UpstreamTransientError(GatewayException):
    """Internal exception representing a transient upstream failure eligible for retry."""

    def __init__(self, message: str, status_code: int = 503) -> None:
        super().__init__(
            code="UPSTREAM_UNAVAILABLE",
            message=message,
            status_code=status_code,
        )


def is_transient_error(exc: BaseException) -> bool:
    """Determine whether an exception represents a transient failure that should be retried.

    Retried:
      - httpx.TimeoutException (connect/read timeouts)
      - httpx.NetworkError (connection dropped, DNS lookup failure)
      - UpstreamTransientError (500, 502, 503, 504)

    NOT Retried:
      - UpstreamBadRequestError (400, 422 - invalid params, context length exceeded)
      - ProviderConfigurationError (401, 403 - bad API keys, permission denied)
    """
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, UpstreamTransientError)):
        return True
    return False


class LLMProvider(ABC):
    """Abstract interface that all upstream provider adapters must implement."""

    provider_name: str

    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = http_client

    async def get_client(self) -> httpx.AsyncClient:
        """Return provided HTTP client or instantiate a configured one."""
        if self._client is not None and not self._client.is_closed:
            return self._client
        self._client = httpx.AsyncClient(timeout=self.settings.upstream_timeout_seconds)
        return self._client

    async def generate(self, request: ChatRequest, request_id: str) -> LLMResponse:
        """Execute chat completion with automatic retries for transient failures."""
        max_retries = self.settings.max_retries
        backoff_factor = self.settings.retry_backoff_factor

        def log_retry(retry_state: RetryCallState) -> None:
            attempt = retry_state.attempt_number
            exc = retry_state.outcome.exception() if retry_state.outcome else None
            logger.warning(
                "Upstream provider call failed; retrying",
                provider=self.provider_name,
                model=request.model,
                request_id=request_id,
                attempt=attempt,
                max_retries=max_retries,
                error=str(exc),
            )

        start_time = time.perf_counter()
        try:
            async for attempt in AsyncRetrying(
                reraise=True,
                stop=stop_after_attempt(max_retries),
                wait=wait_exponential(multiplier=backoff_factor, min=0.5, max=10),
                retry=retry_if_exception(is_transient_error),
                before_sleep=log_retry,
            ):
                with attempt:
                    response = await self._call_provider(request, request_id)
                    latency_ms = (time.perf_counter() - start_time) * 1000
                    response.latency_ms = round(latency_ms, 2)
                    return response

        except httpx.TimeoutException as exc:
            logger.error(
                "Upstream provider timed out after retries",
                provider=self.provider_name,
                request_id=request_id,
                error=str(exc),
            )
            raise UpstreamTimeoutError(
                f"The upstream provider '{self.provider_name}' timed out."
            ) from exc

        except UpstreamTransientError as exc:
            logger.error(
                "Upstream provider unavailable after retries",
                provider=self.provider_name,
                request_id=request_id,
                error=str(exc),
            )
            raise UpstreamUnavailableError(
                f"The upstream provider '{self.provider_name}' is unavailable: {exc.message}"
            ) from exc

        except httpx.NetworkError as exc:
            logger.error(
                "Network failure connecting to provider after retries",
                provider=self.provider_name,
                request_id=request_id,
                error=str(exc),
            )
            raise UpstreamUnavailableError(
                f"Network error connecting to provider '{self.provider_name}'."
            ) from exc

        raise UpstreamUnavailableError(
            f"Failed to communicate with provider '{self.provider_name}'."
        )

    @abstractmethod
    async def _call_provider(self, request: ChatRequest, request_id: str) -> LLMResponse:
        """Internal provider-specific implementation (unwrapped by retries)."""
        pass

    def _handle_http_error(self, status_code: int, response_text: str, request_id: str) -> None:
        """Translate upstream HTTP status codes into standardized GatewayExceptions."""
        if status_code in (401, 403):
            logger.error(
                "Upstream provider authentication failed",
                provider=self.provider_name,
                status_code=status_code,
                request_id=request_id,
            )
            raise ProviderConfigurationError(
                f"Upstream provider '{self.provider_name}' rejected credentials."
            )
        elif status_code in (400, 422):
            logger.warning(
                "Upstream provider rejected invalid payload",
                provider=self.provider_name,
                status_code=status_code,
                request_id=request_id,
                body=response_text[:500],
            )
            raise UpstreamBadRequestError(
                f"Upstream provider '{self.provider_name}' rejected request: {response_text[:300]}"
            )
        elif status_code in (429, 500, 502, 503, 504):
            # Transient failures that qualify for retry
            raise UpstreamTransientError(
                f"Upstream provider returned HTTP {status_code}: {response_text[:200]}",
                status_code=status_code,
            )
        else:
            raise UpstreamTransientError(
                f"Unexpected HTTP {status_code} from provider '{self.provider_name}'.",
                status_code=status_code,
            )
