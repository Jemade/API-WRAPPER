"""Main FastAPI application entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dependencies import _redis_client
from app.api.errors import register_error_handlers
from app.api.v1.router import api_v1_router
from app.api.v1.system import router as system_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import close_db_engine
from app.middleware.correlation import CorrelationIdMiddleware
from app.middleware.logging import RequestLoggingMiddleware

logger = get_logger("main")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application startup and shutdown lifespan context."""
    settings = get_settings()
    configure_logging(
        log_level=settings.log_level,
        is_dev=(settings.app_env == "development"),
    )
    logger.info(
        "Starting Production LLM API Gateway",
        env=settings.app_env,
        version=settings.app_version,
        rate_limit=settings.rate_limit_per_minute,
        redis_failure_policy=settings.rate_limit_redis_failure_policy,
    )
    yield

    # Clean up database and Redis pools on shutdown
    logger.info("Shutting down gateway; releasing connection pools")
    await close_db_engine()
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None


def create_application() -> FastAPI:
    """Factory creating and configuring the FastAPI application instance."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Production-grade LLM API Gateway proxying requests to OpenAI and Anthropic "
            "with API-key authentication, distributed rate limiting, transient error retries, "
            "and HMAC-signed webhook delivery."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    register_error_handlers(app)

    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Request-ID",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
            "X-RateLimit-Degraded",
        ],
    )

    app.include_router(system_router)
    app.include_router(api_v1_router)

    return app


app = create_application()
