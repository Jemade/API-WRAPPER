"""Schemas for health, readiness, and metrics endpoints."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness probe response."""

    status: str = Field(default="ok", description="Service status.")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp.")
    version: str = Field(..., description="Application version.")


class ComponentHealth(BaseModel):
    """Status of an individual dependency."""

    status: str = Field(..., description="'healthy' or 'unhealthy'.")
    message: str | None = Field(default=None, description="Diagnostic message if degraded.")


class ReadyResponse(BaseModel):
    """Readiness probe response covering all downstream dependencies."""

    status: str = Field(..., description="'ready' or 'not_ready'.")
    database: ComponentHealth
    redis: ComponentHealth
    timestamp: str


class MetricsResponse(BaseModel):
    """Service operational metrics."""

    total_requests: int = Field(default=0, ge=0)
    successful_requests: int = Field(default=0, ge=0)
    failed_requests: int = Field(default=0, ge=0)
    average_latency_ms: float = Field(default=0.0, ge=0.0)
    active_rate_limits: int = Field(default=0, ge=0)
