"""Standardized gateway exception hierarchy."""

from typing import Any


class GatewayException(Exception):
    """Base exception for all API gateway errors."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class InvalidRequestError(GatewayException):
    """Client request payload is malformed or invalid."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            code="INVALID_REQUEST",
            message=message,
            status_code=422,
            details=details,
        )


class UnauthorizedError(GatewayException):
    """Authentication failed (missing, invalid, or inactive API key)."""

    def __init__(self, message: str = "Invalid or missing API key.") -> None:
        super().__init__(
            code="UNAUTHORIZED",
            message=message,
            status_code=401,
        )


class RateLimitExceededError(GatewayException):
    """Client has exceeded their allocated rate limit."""

    def __init__(
        self,
        message: str = "Rate limit exceeded. Please retry later.",
        retry_after: int | None = None,
    ) -> None:
        details = {"retry_after": retry_after} if retry_after is not None else {}
        super().__init__(
            code="RATE_LIMITED",
            message=message,
            status_code=429,
            details=details,
        )
        self.retry_after = retry_after


class UpstreamTimeoutError(GatewayException):
    """Upstream model provider timed out."""

    def __init__(self, message: str = "The upstream model provider timed out.") -> None:
        super().__init__(
            code="UPSTREAM_TIMEOUT",
            message=message,
            status_code=504,
        )


class UpstreamBadRequestError(GatewayException):
    """Upstream provider rejected the forwarded request (e.g. context length exceeded)."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            code="UPSTREAM_BAD_REQUEST",
            message=message,
            status_code=502,
            details=details,
        )


class UpstreamUnavailableError(GatewayException):
    """Upstream model provider is temporarily unavailable or returned 5xx."""

    def __init__(
        self, message: str = "The upstream model provider is currently unavailable."
    ) -> None:
        super().__init__(
            code="UPSTREAM_UNAVAILABLE",
            message=message,
            status_code=503,
        )


class ProviderConfigurationError(GatewayException):
    """Requested provider is not configured or missing credentials."""

    def __init__(self, message: str) -> None:
        super().__init__(
            code="PROVIDER_CONFIGURATION_ERROR",
            message=message,
            status_code=500,
        )


class WebhookDeliveryError(GatewayException):
    """Webhook delivery failed after maximum retry attempts."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            code="WEBHOOK_DELIVERY_FAILED",
            message=message,
            status_code=500,
            details=details,
        )


class InternalGatewayError(GatewayException):
    """Unexpected internal gateway error."""

    def __init__(self, message: str = "An internal error occurred.") -> None:
        super().__init__(
            code="INTERNAL_ERROR",
            message=message,
            status_code=500,
        )
