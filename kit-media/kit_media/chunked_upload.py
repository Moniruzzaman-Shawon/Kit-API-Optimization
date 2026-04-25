from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from kit_core import RedisClient, get_logger
from kit_core.exceptions import MediaError

if TYPE_CHECKING:
    from kit_media.adapters import StorageAdapter

logger = get_logger(__name__)


class UploadStatus(str, Enum):
    INITIATED = "initiated"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABORTED = "aborted"


@dataclass
class UploadProgress:
    upload_id: str
    bucket: str
    key: str
    total_parts: int
    completed_parts: int
    status: UploadStatus


class ChunkedUploader:
    """Manages multipart / chunked uploads with progress tracking in Redis."""

    REDIS_PREFIX = "kit:media:upload:"

    def __init__(
        self,
        adapter: StorageAdapter,
        redis: RedisClient | None = None,
    ) -> None:
        self._adapter = adapter
        self._redis = redis or RedisClient.get_instance()

    async def initiate(
        self,
        bucket: str,
        key: str,
        content_type: str,
        expected_parts: int | None = None,
    ) -> str:
        """Start a new multipart upload and return the upload ID."""
        upload_id = await self._adapter.initiate_multipart_upload(
            bucket=bucket,
            key=key,
            content_type=content_type,
        )
        state = {
            "bucket": bucket,
            "key": key,
            "content_type": content_type,
            "status": UploadStatus.INITIATED.value,
            "total_parts": expected_parts or 0,
            "completed_parts": 0,
            "parts": {},
        }
        await self._redis.set(
            f"{self.REDIS_PREFIX}{upload_id}",
            json.dumps(state),
            ttl=86400,
        )
        logger.info("multipart_upload_initiated", upload_id=upload_id, bucket=bucket, key=key)
        return upload_id

    async def upload_part(
        self,
        upload_id: str,
        part_number: int,
        data: bytes,
    ) -> str:
        """Upload a single part and return its ETag."""
        state = await self._get_state(upload_id)
        bucket, key = state["bucket"], state["key"]

        etag = await self._adapter.upload_part(
            bucket=bucket,
            key=key,
            upload_id=upload_id,
            part_number=part_number,
            data=data,
        )

        state["parts"][str(part_number)] = etag
        state["completed_parts"] = len(state["parts"])
        state["status"] = UploadStatus.IN_PROGRESS.value
        await self._redis.set(
            f"{self.REDIS_PREFIX}{upload_id}",
            json.dumps(state),
            ttl=86400,
        )
        logger.info("part_uploaded", upload_id=upload_id, part_number=part_number)
        return etag

    async def complete(
        self,
        upload_id: str,
        parts: list[tuple[int, str]] | None = None,
    ) -> str:
        """Complete the multipart upload. Returns the final object location."""
        state = await self._get_state(upload_id)

        if parts is None:
            parts = [
                (int(num), etag)
                for num, etag in sorted(state["parts"].items(), key=lambda x: int(x[0]))
            ]

        location = await self._adapter.complete_multipart_upload(
            bucket=state["bucket"],
            key=state["key"],
            upload_id=upload_id,
            parts=parts,
        )

        state["status"] = UploadStatus.COMPLETED.value
        await self._redis.set(
            f"{self.REDIS_PREFIX}{upload_id}",
            json.dumps(state),
            ttl=3600,
        )
        logger.info("multipart_upload_completed", upload_id=upload_id, location=location)
        return location

    async def abort(self, upload_id: str) -> None:
        """Abort a multipart upload and clean up."""
        state = await self._get_state(upload_id)

        await self._adapter.abort_multipart_upload(
            bucket=state["bucket"],
            key=state["key"],
            upload_id=upload_id,
        )

        state["status"] = UploadStatus.ABORTED.value
        await self._redis.set(
            f"{self.REDIS_PREFIX}{upload_id}",
            json.dumps(state),
            ttl=3600,
        )
        logger.info("multipart_upload_aborted", upload_id=upload_id)

    async def get_progress(self, upload_id: str) -> UploadProgress:
        """Get the current progress of an upload."""
        state = await self._get_state(upload_id)
        return UploadProgress(
            upload_id=upload_id,
            bucket=state["bucket"],
            key=state["key"],
            total_parts=state["total_parts"],
            completed_parts=state["completed_parts"],
            status=UploadStatus(state["status"]),
        )

    async def _get_state(self, upload_id: str) -> dict:
        raw = await self._redis.get(f"{self.REDIS_PREFIX}{upload_id}")
        if raw is None:
            raise MediaError(f"Upload {upload_id} not found or expired")
        return json.loads(raw)
