"""Webhook delivery audit model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.generation import GenerationRequest


class WebhookDelivery(Base, TimestampMixin):
    """Audit log and retry status for webhook event deliveries."""

    __tablename__ = "webhook_deliveries"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    request_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("generation_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    webhook_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        default="PENDING",
        nullable=False,
        index=True,
    )  # PENDING, DELIVERED, FAILED
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    generation_request: Mapped["GenerationRequest"] = relationship(
        "GenerationRequest",
        back_populates="webhook_deliveries",
    )
