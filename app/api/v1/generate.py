"""POST /v1/generate endpoint."""

import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_client, get_db, get_rate_limiter
from app.core.correlation import get_request_id
from app.core.exceptions import RateLimitExceededError
from app.models.api_key import ApiKey
from app.schemas.error import ErrorResponse
from app.schemas.generate import ChatRequest
from app.schemas.response import LLMResponse
from app.services.generation import GenerationService
from app.services.rate_limiter import RateLimiter

router = APIRouter(tags=["Generation"])


@router.post(
    "/generate",
    response_model=LLMResponse,
    responses={
        200: {"description": "Successful generation response", "model": LLMResponse},
        401: {"description": "Unauthorized - Missing or invalid API key", "model": ErrorResponse},
        422: {"description": "Invalid Request - Validation failure", "model": ErrorResponse},
        429: {"description": "Rate Limited - Exceeded allowed quota", "model": ErrorResponse},
        502: {"description": "Upstream Bad Request", "model": ErrorResponse},
        503: {"description": "Upstream Unavailable", "model": ErrorResponse},
        504: {"description": "Upstream Timeout", "model": ErrorResponse},
    },
    summary="Submit a chat completion generation request",
    description=(
        "Authenticates the client, enforces rate limits, validates the payload, "
        "and forwards the request to the target model provider. Returns a normalized response "
        "or dispatches a signed webhook if `webhook_url` is specified."
    ),
)
async def generate_chat_completion(
    request_body: ChatRequest,
    _req: Request,
    client: ApiKey = Depends(get_current_client),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    request_id = get_request_id()

    limit_result = await rate_limiter.check_rate_limit(
        key_identifier=client.key_hash,
        limit_override=client.rate_limit_per_minute,
    )

    if not limit_result.allowed:
        retry_after = max(1, limit_result.reset_epoch - int(time.time()))
        raise RateLimitExceededError(
            message=(
                f"Rate limit of {limit_result.limit} requests/minute exceeded. "
                f"Try again in {retry_after}s."
            ),
            retry_after=retry_after,
        )

    gen_service = GenerationService(db_session=db)
    result = await gen_service.execute(
        request=request_body,
        client_api_key=client,
        request_id=request_id,
    )

    return JSONResponse(
        status_code=200,
        content=result.model_dump(),
        headers=limit_result.headers,
    )
