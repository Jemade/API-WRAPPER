"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the API Gateway."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Production LLM API Gateway"
    app_version: str = "0.1.0"
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"

    # Server
    host: str = "0.0.0.0"
    port: int = 8080

    # Security
    webhook_secret: str = Field(
        default="change-me-in-production-must-be-at-least-32-chars",
        description="Shared secret for HMAC-SHA256 webhook signatures",
    )
    cors_origins: str = "*"

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/gateway",
        description="SQLAlchemy async connection string",
    )

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for distributed rate limiting",
    )

    # Rate Limiting
    rate_limit_per_minute: int = Field(
        default=60,
        description="Default requests per minute allowed per client API key",
    )
    rate_limit_redis_failure_policy: Literal["fail_open", "fail_closed"] = Field(
        default="fail_open",
        description=(
            "Policy when Redis is unreachable: 'fail_open' allows requests through to prevent "
            "gateway outage; 'fail_closed' rejects with 429 to protect upstream capacity."
        ),
    )

    # Providers
    openai_api_key: str | None = None
    openai_api_base: str = "https://api.openai.com/v1"

    anthropic_api_key: str | None = None
    anthropic_api_base: str = "https://api.anthropic.com/v1"

    # Resiliency & Retries
    upstream_timeout_seconds: float = 30.0
    max_retries: int = 3
    retry_backoff_factor: float = 1.5

    # Webhooks
    webhook_timeout_seconds: float = 10.0
    webhook_max_retries: int = 3

    # Request limits
    max_request_size_bytes: int = 2 * 1024 * 1024  # 2MB
    log_request_content: bool = False

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        if not self.cors_origins:
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
