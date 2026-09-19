"""System, health, readiness, and metrics endpoints."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Response, status
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_redis
from app.core.config import get_settings
from app.schemas.health import ComponentHealth, HealthResponse, MetricsResponse, ReadyResponse

router = APIRouter(tags=["System"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness health check",
    description="Returns 200 OK if the gateway process is running and able to handle HTTP traffic.",
)
async def health_check() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        timestamp=datetime.now(UTC).isoformat(),
        version=settings.app_version,
    )


@router.get(
    "/ready",
    response_model=ReadyResponse,
    responses={
        200: {"description": "All downstream dependencies are healthy and operational"},
        503: {"description": "One or more downstream dependencies are unreachable"},
    },
    summary="Readiness probe",
    description="Verifies operational connectivity to both PostgreSQL and Redis.",
)
async def readiness_check(
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> ReadyResponse:
    db_health = ComponentHealth(status="healthy")
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        db_health.status = "unhealthy"
        db_health.message = f"Database ping failed: {str(exc)}"

    redis_health = ComponentHealth(status="healthy")
    try:
        await redis.ping()
    except Exception as exc:
        redis_health.status = "unhealthy"
        redis_health.message = f"Redis ping failed: {str(exc)}"

    is_ready = db_health.status == "healthy" and redis_health.status == "healthy"
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadyResponse(
        status="ready" if is_ready else "not_ready",
        database=db_health,
        redis=redis_health,
        timestamp=datetime.now(UTC).isoformat(),
    )


@router.get(
    "/metrics",
    response_model=MetricsResponse,
    summary="Service operational metrics",
    description="Returns aggregated operational statistics for requests and rate limits.",
)
async def service_metrics(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> MetricsResponse:
    total_reqs = 0
    success_reqs = 0
    failed_reqs = 0
    avg_latency = 0.0

    try:
        stats_query = text(
            "SELECT "
            "  COUNT(*) AS total, "
            "  COUNT(CASE WHEN status = 'success' THEN 1 END) AS successful, "
            "  COUNT(CASE WHEN status = 'failed' THEN 1 END) AS failed, "
            "  COALESCE(AVG(latency_ms), 0.0) AS avg_latency "
            "FROM generation_requests"
        )
        result = await db.execute(stats_query)
        row = result.mappings().one_or_none()
        if row:
            total_reqs = int(row["total"])
            success_reqs = int(row["successful"])
            failed_reqs = int(row["failed"])
            avg_latency = round(float(row["avg_latency"]), 2)
    except Exception:
        pass

    active_rate_limits = 0
    try:
        keys = await redis.keys("ratelimit:*")
        active_rate_limits = len(keys)
    except Exception:
        pass

    return MetricsResponse(
        total_requests=total_reqs,
        successful_requests=success_reqs,
        failed_requests=failed_reqs,
        average_latency_ms=avg_latency,
        active_rate_limits=active_rate_limits,
    )
