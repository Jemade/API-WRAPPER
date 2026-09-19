"""Webhook dispatch, HMAC signing, and resilient delivery."""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import compute_webhook_signature
from app.models.webhook import WebhookDelivery
from app.schemas.webhook import WebhookEvent

logger = get_logger("services.webhook")


class WebhookService:
    """Delivers HMAC-signed webhook events with retry handling and DB audit persistence."""

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self.settings = get_settings()
        self._client = http_client

    async def get_client(self) -> httpx.AsyncClient:
        """Return provided HTTP client or instantiate a configured one."""
        if self._client is not None and not self._client.is_closed:
            return self._client
        self._client = httpx.AsyncClient(timeout=self.settings.webhook_timeout_seconds)
        return self._client

    async def dispatch(
        self,
        webhook_url: str,
        request_id: str,
        event_type: str,
        payload: dict[str, Any],
        db_session: AsyncSession | None = None,
    ) -> bool:
        """Construct, sign, and deliver a webhook event asynchronously.

        Tracks attempts and status in the webhook_deliveries table.
        """
        event_id = f"evt_{uuid.uuid4().hex}"
        now_utc = datetime.now(UTC)
        timestamp_str = now_utc.isoformat()

        event = WebhookEvent(
            event_id=event_id,
            timestamp=timestamp_str,
            request_id=request_id,
            event_type=event_type,  # type: ignore[arg-type]
            payload=payload,
        )

        raw_payload = json.dumps(event.model_dump(), separators=(",", ":")).encode("utf-8")
        signature = compute_webhook_signature(raw_payload, self.settings.webhook_secret)

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Production-LLM-Gateway-Webhook/0.1.0",
            "X-Webhook-ID": event_id,
            "X-Webhook-Timestamp": timestamp_str,
            "X-Webhook-Signature": f"v1={signature}",
            "X-Request-ID": request_id,
        }

        delivery_record: WebhookDelivery | None = None
        if db_session is not None:
            delivery_record = WebhookDelivery(
                request_id=request_id,
                webhook_url=webhook_url,
                event_type=event_type,
                status="PENDING",
                attempts=0,
            )
            db_session.add(delivery_record)
            await db_session.commit()

        client = await self.get_client()
        max_retries = self.settings.webhook_max_retries
        attempts = 0
        last_error = ""

        def log_retry(retry_state: RetryCallState) -> None:
            logger.warning(
                "Webhook delivery attempt failed; retrying",
                webhook_url=webhook_url,
                request_id=request_id,
                event_id=event_id,
                attempt=retry_state.attempt_number,
                error=str(retry_state.outcome.exception()) if retry_state.outcome else None,
            )

        try:
            async for attempt in AsyncRetrying(
                reraise=True,
                stop=stop_after_attempt(max_retries),
                wait=wait_exponential(multiplier=1.0, min=0.5, max=5),
                retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
                before_sleep=log_retry,
            ):
                with attempt:
                    attempts += 1
                    resp = await client.post(
                        webhook_url,
                        content=raw_payload,
                        headers=headers,
                    )
                    resp.raise_for_status()

            logger.info(
                "Webhook delivered successfully",
                webhook_url=webhook_url,
                request_id=request_id,
                event_id=event_id,
                attempts=attempts,
            )
            if delivery_record and db_session:
                delivery_record.status = "DELIVERED"
                delivery_record.attempts = attempts
                delivery_record.last_attempt_at = datetime.now(UTC)
                await db_session.commit()
            return True

        except Exception as exc:
            last_error = str(exc)
            logger.error(
                "Webhook delivery permanently failed",
                webhook_url=webhook_url,
                request_id=request_id,
                event_id=event_id,
                attempts=attempts,
                error=last_error,
            )
            if delivery_record and db_session:
                delivery_record.status = "FAILED"
                delivery_record.attempts = attempts
                delivery_record.last_attempt_at = datetime.now(UTC)
                delivery_record.error_message = last_error
                await db_session.commit()
            return False
