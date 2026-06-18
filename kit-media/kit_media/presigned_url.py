from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kit_media.adapters import StorageAdapter


@dataclass(frozen=True)
class PresignedURL:
    """A presigned URL with optional form fields and expiry."""

    url: str
    fields: dict[str, str] = field(default_factory=dict)
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class PresignedURLGenerator:
    """Generates presigned URLs for upload and download operations."""

    def __init__(self, adapter: StorageAdapter) -> None:
        self._adapter = adapter

    async def generate_upload_url(
        self,
        bucket: str,
        key: str,
        content_type: str,
        expires: int = 3600,
        conditions: list[Any] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> PresignedURL:
        """Generate a presigned URL for uploading an object.

        Args:
            bucket: Target bucket name.
            key: Object key / path.
            content_type: MIME type of the upload.
            expires: URL validity in seconds.
            conditions: Optional policy conditions for POST uploads.
            metadata: Optional metadata to attach to the object.

        Returns:
            A PresignedURL with the upload URL and any required form fields.
        """
        return await self._adapter.create_presigned_upload(
            bucket=bucket,
            key=key,
            content_type=content_type,
            expires=expires,
            conditions=conditions,
            metadata=metadata,
        )

    async def generate_download_url(
        self,
        bucket: str,
        key: str,
        expires: int = 3600,
        filename: str | None = None,
    ) -> str:
        """Generate a presigned URL for downloading an object.

        Args:
            bucket: Source bucket name.
            key: Object key / path.
            expires: URL validity in seconds.
            filename: Optional filename for Content-Disposition header.

        Returns:
            A presigned download URL string.
        """
        return await self._adapter.create_presigned_download(
            bucket=bucket,
            key=key,
            expires=expires,
            filename=filename,
        )
