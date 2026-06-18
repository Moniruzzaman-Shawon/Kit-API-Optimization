from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from functools import partial
from typing import Any

from kit_media.presigned_url import PresignedURL


class GCSAdapter:
    """Google Cloud Storage adapter."""

    def __init__(
        self,
        project: str | None = None,
        credentials_path: str | None = None,
    ) -> None:
        from google.cloud import storage

        if credentials_path:
            self._client = storage.Client.from_service_account_json(
                credentials_path, project=project
            )
        else:
            self._client = storage.Client(project=project)

    async def create_presigned_upload(
        self,
        bucket: str,
        key: str,
        content_type: str,
        expires: int = 3600,
        conditions: list[Any] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> PresignedURL:
        blob = self._client.bucket(bucket).blob(key)
        if metadata:
            blob.metadata = metadata

        loop = asyncio.get_event_loop()
        url = await loop.run_in_executor(
            None,
            partial(
                blob.generate_signed_url,
                version="v4",
                expiration=timedelta(seconds=expires),
                method="PUT",
                content_type=content_type,
            ),
        )

        return PresignedURL(
            url=url,
            fields={"Content-Type": content_type},
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires),
        )

    async def create_presigned_download(
        self,
        bucket: str,
        key: str,
        expires: int = 3600,
        filename: str | None = None,
    ) -> str:
        blob = self._client.bucket(bucket).blob(key)

        kwargs: dict[str, Any] = {
            "version": "v4",
            "expiration": timedelta(seconds=expires),
            "method": "GET",
        }
        if filename:
            kwargs["response_disposition"] = f'attachment; filename="{filename}"'

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            partial(blob.generate_signed_url, **kwargs),
        )

    async def initiate_multipart_upload(
        self,
        bucket: str,
        key: str,
        content_type: str,
    ) -> str:
        import httpx

        blob = self._client.bucket(bucket).blob(key)
        loop = asyncio.get_event_loop()
        url = await loop.run_in_executor(
            None,
            partial(
                blob.generate_signed_url,
                version="v4",
                expiration=timedelta(hours=24),
                method="POST",
                content_type=content_type,
                headers={"x-goog-resumable": "start"},
            ),
        )

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={
                    "Content-Type": content_type,
                    "x-goog-resumable": "start",
                },
            )
            resp.raise_for_status()
            return resp.headers["Location"]

    async def upload_part(
        self,
        bucket: str,
        key: str,
        upload_id: str,
        part_number: int,
        data: bytes,
    ) -> str:
        import hashlib

        import httpx

        offset = (part_number - 1) * len(data)
        async with httpx.AsyncClient() as client:
            resp = await client.put(
                upload_id,
                content=data,
                headers={
                    "Content-Range": f"bytes {offset}-{offset + len(data) - 1}/*",
                },
            )
            resp.raise_for_status()

        return hashlib.md5(data).hexdigest()

    async def complete_multipart_upload(
        self,
        bucket: str,
        key: str,
        upload_id: str,
        parts: list[tuple[int, str]],
    ) -> str:
        return f"gs://{bucket}/{key}"

    async def abort_multipart_upload(
        self,
        bucket: str,
        key: str,
        upload_id: str,
    ) -> None:
        import httpx

        async with httpx.AsyncClient() as client:
            await client.delete(upload_id)
