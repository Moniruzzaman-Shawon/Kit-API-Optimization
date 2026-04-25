from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from redis import Redis


class ProcessStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class WebhookEvent:
    """Normalized webhook event across payment providers."""

    id: str
    type: str
    provider: str
    data: dict[str, Any]
    timestamp: float
    raw: bytes | str


@dataclass
class ProcessResult:
    """Result of processing a webhook event."""

    event_id: str
    status: ProcessStatus
    handler_results: list[Any] = field(default_factory=list)
    error: str | None = None


class WebhookReceiver:
    """Receives, verifies, and dispatches payment provider webhooks."""

    def __init__(self, redis: Redis, prefix: str = "kit:webhook") -> None:
        self._redis = redis
        self._prefix = prefix
        self._handlers: dict[str, list[Callable[[WebhookEvent], Any]]] = {}

    # ------------------------------------------------------------------
    # Signature verification
    # ------------------------------------------------------------------

    def verify(self, payload: bytes, signature: str, secret: str) -> bool:
        """Verify a webhook payload signature using HMAC-SHA256."""
        expected = hmac.new(
            secret.encode(),
            payload if isinstance(payload, bytes) else payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    # ------------------------------------------------------------------
    # Event parsing / normalisation
    # ------------------------------------------------------------------

    def parse(self, payload: bytes | str, provider: str) -> WebhookEvent:
        """Parse a raw webhook payload into a normalised ``WebhookEvent``."""
        raw = payload
        if isinstance(payload, bytes):
            data = json.loads(payload)
        else:
            data = json.loads(payload)

        event_id = self._extract_event_id(data, provider)
        event_type = self._extract_event_type(data, provider)
        timestamp = self._extract_timestamp(data, provider)

        return WebhookEvent(
            id=event_id,
            type=event_type,
            provider=provider,
            data=data,
            timestamp=timestamp,
            raw=raw,
        )

    # ------------------------------------------------------------------
    # Handler registration and dispatch
    # ------------------------------------------------------------------

    def register_handler(
        self,
        event_type: str,
        handler: Callable[[WebhookEvent], Any],
    ) -> None:
        """Register a handler for a given event type."""
        self._handlers.setdefault(event_type, []).append(handler)

    def process(self, event: WebhookEvent) -> ProcessResult:
        """Dispatch an event to all registered handlers, deduplicating by event ID."""
        dedup_key = f"{self._prefix}:seen:{event.id}"

        if self._redis.get(dedup_key):
            return ProcessResult(
                event_id=event.id,
                status=ProcessStatus.SKIPPED,
                error="duplicate event",
            )

        handlers = self._handlers.get(event.type, [])
        if not handlers:
            self._redis.set(dedup_key, "1", ex=86400)
            return ProcessResult(event_id=event.id, status=ProcessStatus.SUCCESS)

        results: list[Any] = []
        try:
            for handler in handlers:
                results.append(handler(event))
            self._redis.set(dedup_key, "1", ex=86400)
            return ProcessResult(
                event_id=event.id,
                status=ProcessStatus.SUCCESS,
                handler_results=results,
            )
        except Exception as exc:
            return ProcessResult(
                event_id=event.id,
                status=ProcessStatus.FAILED,
                handler_results=results,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_event_id(data: dict[str, Any], provider: str) -> str:
        if provider == "stripe":
            return data.get("id", "")
        if provider == "paddle":
            return data.get("event_id", data.get("notification_id", ""))
        return data.get("id", data.get("event_id", ""))

    @staticmethod
    def _extract_event_type(data: dict[str, Any], provider: str) -> str:
        if provider == "stripe":
            return data.get("type", "")
        if provider == "paddle":
            return data.get("event_type", "")
        return data.get("type", data.get("event_type", ""))

    @staticmethod
    def _extract_timestamp(data: dict[str, Any], provider: str) -> float:
        if provider == "stripe":
            return float(data.get("created", time.time()))
        if provider == "paddle":
            return float(data.get("occurred_at", time.time()))
        return float(data.get("timestamp", time.time()))
