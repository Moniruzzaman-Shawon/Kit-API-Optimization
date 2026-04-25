from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from functools import partial
from typing import Any

from kit_media.presigned_url import PresignedURL


class S3Adapter:
    """AWS S3 storage adapter using boto3."""

    def __init__(
        self,
        region: str = "us-east-1",
        endpoint_url: str | None = None,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
    ) -> None:
        import boto3

        self._client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )

    async def create_presigned_upload(
        self,
        bucket: str,
        key: str,
        content_type: str,
        expires: int = 3600,
        conditions: list[Any] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> PresignedURL:
        conditions = conditions or []
        conditions.append({"Content-Type": content_type})

        fields = {"Content-Type": content_type}
        if metadata:
            for k, v in metadata.items():
                fields[f"x-amz-meta-{k}"] = v
                conditions.append({f"x-amz-meta-{k}": v})

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            partial(
                self._client.generate_presigned_post,
                Bucket=bucket,
                Key=key,
                Fields=fields,
                Conditions=conditions,
                ExpiresIn=expires,
            ),
        )

        return PresignedURL(
            url=result["url"],
            fields=result["fields"],
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires),
        )

    async def create_presigned_download(
        self,
        bucket: str,
        key: str,
        expires: int = 3600,
        filename: str | None = None,
    ) -> str:
        params: dict[str, Any] = {"Bucket": bucket, "Key": key}
        if filename:
            params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            partial(
                self._client.generate_presigned_url,
                "get_object",
                Params=params,
                ExpiresIn=expires,
            ),
        )

    async def initiate_multipart_upload(
        self,
        bucket: str,
        key: str,
        content_type: str,
    ) -> str:
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None,
            partial(
                self._client.create_multipart_upload,
                Bucket=bucket,
                Key=key,
                ContentType=content_type,
            ),
        )
        return resp["UploadId"]

    async def upload_part(
        self,
        bucket: str,
        key: str,
        upload_id: str,
        part_number: int,
        data: bytes,
    ) -> str:
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None,
            partial(
                self._client.upload_part,
                Bucket=bucket,
                Key=key,
                UploadId=upload_id,
                PartNumber=part_number,
                Body=data,
            ),
        )
        return resp["ETag"]

    async def complete_multipart_upload(
        self,
        bucket: str,
        key: str,
        upload_id: str,
        parts: list[tuple[int, str]],
    ) -> str:
        multipart = {
            "Parts": [
                {"PartNumber": num, "ETag": etag}
                for num, etag in sorted(parts)
            ]
        }
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None,
            partial(
                self._client.complete_multipart_upload,
                Bucket=bucket,
                Key=key,
                UploadId=upload_id,
                MultipartUpload=multipart,
            ),
        )
        return resp.get("Location", f"s3://{bucket}/{key}")

    async def abort_multipart_upload(
        self,
        bucket: str,
        key: str,
        upload_id: str,
    ) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            partial(
                self._client.abort_multipart_upload,
                Bucket=bucket,
                Key=key,
                UploadId=upload_id,
            ),
        )
