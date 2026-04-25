from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from enum import Enum

from kit_core import RedisClient, get_logger
from kit_core.exceptions import MediaError

logger = get_logger(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class CaptionSegment:
    start: float
    end: float
    text: str


@dataclass
class CaptionResult:
    text: str
    segments: list[CaptionSegment] = field(default_factory=list)
    language: str | None = None
    duration: float | None = None


class CaptionJob:
    """Manages async media captioning / transcription jobs with Redis state tracking."""

    REDIS_PREFIX = "kit:media:caption:"

    def __init__(
        self,
        redis: RedisClient | None = None,
        job_ttl: int = 86400,
    ) -> None:
        self._redis = redis or RedisClient.get_instance()
        self._job_ttl = job_ttl

    async def submit(
        self,
        media_url: str,
        language: str | None = None,
        callback_url: str | None = None,
    ) -> str:
        """Submit a new captioning job. Returns the job ID."""
        job_id = uuid.uuid4().hex
        state = {
            "job_id": job_id,
            "media_url": media_url,
            "language": language,
            "callback_url": callback_url,
            "status": JobStatus.PENDING.value,
            "result": None,
            "error": None,
        }
        await self._redis.set(
            f"{self.REDIS_PREFIX}{job_id}",
            json.dumps(state),
            ttl=self._job_ttl,
        )
        logger.info("caption_job_submitted", job_id=job_id, media_url=media_url)
        return job_id

    async def poll(self, job_id: str) -> JobStatus:
        """Check the current status of a caption job."""
        state = await self._get_state(job_id)
        return JobStatus(state["status"])

    async def get_result(self, job_id: str) -> CaptionResult:
        """Get the result of a completed caption job."""
        state = await self._get_state(job_id)
        status = JobStatus(state["status"])

        if status == JobStatus.FAILED:
            raise MediaError(f"Caption job {job_id} failed: {state.get('error', 'unknown')}")
        if status != JobStatus.COMPLETED:
            raise MediaError(f"Caption job {job_id} is not yet completed (status: {status.value})")

        result_data = state["result"]
        segments = [
            CaptionSegment(start=s["start"], end=s["end"], text=s["text"])
            for s in result_data.get("segments", [])
        ]
        return CaptionResult(
            text=result_data["text"],
            segments=segments,
            language=result_data.get("language"),
            duration=result_data.get("duration"),
        )

    async def update_status(
        self,
        job_id: str,
        status: JobStatus,
        result: CaptionResult | None = None,
        error: str | None = None,
    ) -> None:
        """Update job status (used by the processing backend)."""
        state = await self._get_state(job_id)
        state["status"] = status.value

        if result:
            state["result"] = {
                "text": result.text,
                "segments": [
                    {"start": s.start, "end": s.end, "text": s.text}
                    for s in result.segments
                ],
                "language": result.language,
                "duration": result.duration,
            }

        if error:
            state["error"] = error

        await self._redis.set(
            f"{self.REDIS_PREFIX}{job_id}",
            json.dumps(state),
            ttl=self._job_ttl,
        )
        logger.info("caption_job_updated", job_id=job_id, status=status.value)

    async def _get_state(self, job_id: str) -> dict:
        raw = await self._redis.get(f"{self.REDIS_PREFIX}{job_id}")
        if raw is None:
            raise MediaError(f"Caption job {job_id} not found or expired")
        return json.loads(raw)
