"""Orchestration service for LLM generation, auditing, and webhook triggering."""

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import GatewayException
from app.core.logging import get_logger
from app.models.api_key import ApiKey
from app.models.generation import GenerationRequest
from app.providers.factory import ProviderFactory
from app.schemas.generate import ChatRequest
from app.schemas.response import LLMResponse
from app.services.webhook import WebhookService

logger = get_logger("services.generation")


class GenerationService:
    """Orchestrates request routing, provider execution, DB persistence, and webhooks."""

    def __init__(
        self,
        db_session: AsyncSession,
        http_client: httpx.AsyncClient | None = None,
        provider_factory: ProviderFactory | None = None,
    ) -> None:
        self.db = db_session
        self.factory = provider_factory or ProviderFactory(http_client=http_client)
        self.webhook_service = WebhookService(http_client=http_client)

    async def execute(
        self,
        request: ChatRequest,
        client_api_key: ApiKey,
        request_id: str,
    ) -> LLMResponse:
        """Forward request to resolved provider, record audit log, and dispatch optional webhook."""
        provider_adapter = self.factory.resolve(request.model)
        provider_name = provider_adapter.provider_name

        logger.info(
            "Forwarding generation request",
            request_id=request_id,
            provider=provider_name,
            model=request.model,
            client_id=client_api_key.id,
        )

        try:
            response = await provider_adapter.generate(request, request_id)

        except Exception as exc:
            status = "failed"
            error_code = "INTERNAL_ERROR"
            error_message = str(exc)

            if isinstance(exc, GatewayException):
                error_code = exc.code
                error_message = exc.message

            audit_record = GenerationRequest(
                id=request_id,
                client_id=client_api_key.id,
                provider=provider_name,
                model=request.model,
                status=status,
                latency_ms=0.0,
                error_code=error_code,
                error_message=error_message,
            )
            self.db.add(audit_record)
            await self.db.commit()

            await self._dispatch_webhook(
                request,
                request_id,
                "generation.failed",
                {"code": error_code, "message": error_message, "request_id": request_id},
            )

            raise

        audit_record = GenerationRequest(
            id=request_id,
            client_id=client_api_key.id,
            provider=provider_name,
            model=request.model,
            status="success",
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            total_tokens=response.total_tokens,
            latency_ms=response.latency_ms,
        )
        self.db.add(audit_record)
        await self.db.commit()

        await self._dispatch_webhook(
            request,
            request_id,
            "generation.completed",
            response.model_dump(),
        )
        return response

    async def _dispatch_webhook(
        self,
        request: ChatRequest,
        request_id: str,
        event_type: str,
        payload: dict,
    ) -> None:
        """Keep optional notification failures separate from the generation outcome."""
        if not request.webhook_url:
            return
        try:
            await self.webhook_service.dispatch(
                webhook_url=str(request.webhook_url),
                request_id=request_id,
                event_type=event_type,
                payload=payload,
                db_session=self.db,
            )
        except Exception:
            await self.db.rollback()
            logger.exception(
                "Webhook dispatch failed", request_id=request_id, event_type=event_type
            )
