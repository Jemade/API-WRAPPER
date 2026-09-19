"""Integration tests for system health, readiness, and metrics endpoints."""

import httpx
import pytest

from app.api.dependencies import get_db


@pytest.mark.asyncio
async def test_health_check_endpoint(async_client: httpx.AsyncClient) -> None:
    """GET /health returns 200 OK with version and timestamp."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_readiness_check_healthy(async_client: httpx.AsyncClient) -> None:
    """GET /ready returns 200 OK when both DB and Redis are reachable."""
    response = await async_client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["database"]["status"] == "healthy"
    assert data["redis"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_readiness_check_degraded(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /ready returns 503 Service Unavailable when DB is down."""
    from app.main import app

    async def broken_db():
        class BrokenSession:
            async def execute(self, *args, **kwargs):
                raise ConnectionRefusedError("Database unreachable")

        yield BrokenSession()

    app.dependency_overrides[get_db] = broken_db

    response = await async_client.get("/ready")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "not_ready"
    assert data["database"]["status"] == "unhealthy"


@pytest.mark.asyncio
async def test_metrics_endpoint(async_client: httpx.AsyncClient) -> None:
    """GET /metrics returns aggregated operational metrics."""
    response = await async_client.get("/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "total_requests" in data
    assert "successful_requests" in data
    assert "failed_requests" in data
    assert "average_latency_ms" in data
    assert "active_rate_limits" in data
