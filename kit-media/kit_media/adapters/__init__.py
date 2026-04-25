from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from kit_media.presigned_url import PresignedURL


@runtime_checkable
class StorageAdapter(Protocol):
    """Protocol for cloud storage adapters."""

    async def create_presigned_upload(
        self,
        bucket: str,
        key: str,
        content_type: str,
        expires: int = 3600,
        conditions: list[Any] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> PresignedURL: ...

    async def create_presigned_download(
        self,
        bucket: str,
        key: str,
        expires: int = 3600,
        filename: str | None = None,
    ) -> str: ...

    async def initiate_multipart_upload(
        self,
        bucket: str,
        key: str,
        content_type: str,
    ) -> str: ...

    async def upload_part(
        self,
        bucket: str,
        key: str,
        upload_id: str,
        part_number: int,
        data: bytes,
    ) -> str: ...

    async def complete_multipart_upload(
        self,
        bucket: str,
        key: str,
        upload_id: str,
        parts: list[tuple[int, str]],
    ) -> str: ...

    async def abort_multipart_upload(
        self,
        bucket: str,
        key: str,
        upload_id: str,
    ) -> None: ...


__all__ = ["StorageAdapter"]

# Lazy imports to avoid requiring all provider SDKs
def __getattr__(name: str):
    if name == "S3Adapter":
        from kit_media.adapters.s3_adapter import S3Adapter
        return S3Adapter
    if name == "R2Adapter":
        from kit_media.adapters.r2_adapter import R2Adapter
        return R2Adapter
    if name == "GCSAdapter":
        from kit_media.adapters.gcs_adapter import GCSAdapter
        return GCSAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
