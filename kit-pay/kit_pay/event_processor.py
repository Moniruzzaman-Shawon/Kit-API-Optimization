from __future__ import annotations

import json
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from redis import Redis

from kit_pay.webhook_receiver import WebhookEvent, WebhookReceiver


class EventStatus(Enum):
    RECEIVED = "received"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


@dataclass
class EventRecord:
    """Internal record wrapping a webhook event with processing metadata."""

    event: WebhookEvent
    status: EventStatus
    attempts: int = 0
    last_error: str | None = None
    created_at: float = 0.0
    updated_at: float = 0.0


class EventProcessor:
    """Async-friendly event processing pipeline with retry and dead-letter support."""

    MAX_RETRIES = 5

    def __init__(
        self,
        redis: Redis,
        receiver: WebhookReceiver,
        prefix: str = "kit:events",
    ) -> None:
        self._redis = redis
        self._receiver = receiver
        self._prefix = prefix

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enqueue(self, event: WebhookEvent) -> None:
        """Add an event to the processing queue."""
        now = time.time()
        record = {
            "event": _serialise_event(event),
            "status": EventStatus.RECEIVED.value,
            "attempts": 0,
            "last_error": None,
            "created_at": now,
            "updated_at": now,
        }
        self._redis.lpush(f"{self._prefix}:queue", json.dumps(record))
        self._incr_metric("enqueued")

    def process_batch(self, max_events: int = 100) -> list[EventRecord]:
        """Process up to *max_events* from the queue."""
        results: list[EventRecord] = []
        for _ in range(max_events):
            raw = self._redis.rpop(f"{self._prefix}:queue")
            if raw is None:
                break
            record_data = json.loads(raw)
            event = _deserialise_event(record_data["event"])
            record = EventRecord(
                event=event,
                status=EventStatus.PROCESSING,
                attempts=record_data["attempts"] + 1,
                created_at=record_data["created_at"],
                updated_at=time.time(),
            )

            result = self._receiver.process(event)

            if result.error and result.status.value == "failed":
                record.status = EventStatus.FAILED
                record.last_error = result.error
                self._handle_failure(record)
            else:
                record.status = EventStatus.COMPLETED
                self._incr_metric("completed")

            record.updated_at = time.time()
            results.append(record)

        return results

    def retry_failed(self) -> int:
        """Move failed events back to the processing queue for another attempt.

        Events that have exceeded ``MAX_RETRIES`` are sent to the dead-letter
        queue instead.

        Returns the number of events re-enqueued.
        """
        failed_key = f"{self._prefix}:failed"
        count = 0
        while True:
            raw = self._redis.rpop(failed_key)
            if raw is None:
                break
            record_data = json.loads(raw)
            if record_data["attempts"] >= self.MAX_RETRIES:
                self._redis.lpush(
                    f"{self._prefix}:dead_letter", json.dumps(record_data)
                )
                self._incr_metric("dead_letter")
            else:
                record_data["status"] = EventStatus.RECEIVED.value
                record_data["updated_at"] = time.time()
                self._redis.lpush(
                    f"{self._prefix}:queue", json.dumps(record_data)
                )
                count += 1
                self._incr_metric("retried")
        return count

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def get_metrics(self) -> dict[str, int]:
        """Return processing metrics stored in Redis."""
        keys = ["enqueued", "completed", "failed", "retried", "dead_letter"]
        result: dict[str, int] = {}
        for key in keys:
            val = self._redis.get(f"{self._prefix}:metrics:{key}")
            result[key] = int(val) if val else 0
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _handle_failure(self, record: EventRecord) -> None:
        data = {
            "event": _serialise_event(record.event),
            "status": EventStatus.FAILED.value,
            "attempts": record.attempts,
            "last_error": record.last_error,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }
        if record.attempts >= self.MAX_RETRIES:
            self._redis.lpush(
                f"{self._prefix}:dead_letter", json.dumps(data)
            )
            self._incr_metric("dead_letter")
        else:
            self._redis.lpush(f"{self._prefix}:failed", json.dumps(data))
            self._incr_metric("failed")

    def _incr_metric(self, name: str) -> None:
        self._redis.incr(f"{self._prefix}:metrics:{name}")


# ------------------------------------------------------------------
# Serialisation helpers
# ------------------------------------------------------------------


def _serialise_event(event: WebhookEvent) -> dict[str, Any]:
    raw = event.raw
    if isinstance(raw, bytes):
        raw = raw.decode()
    return {
        "id": event.id,
        "type": event.type,
        "provider": event.provider,
        "data": event.data,
        "timestamp": event.timestamp,
        "raw": raw,
    }


def _deserialise_event(data: dict[str, Any]) -> WebhookEvent:
    return WebhookEvent(
        id=data["id"],
        type=data["type"],
        provider=data["provider"],
        data=data["data"],
        timestamp=data["timestamp"],
        raw=data["raw"],
    )
