from __future__ import annotations

from kit_media.adapters.s3_adapter import S3Adapter


class R2Adapter(S3Adapter):
    """Cloudflare R2 storage adapter (S3-compatible)."""

    def __init__(
        self,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
    ) -> None:
        super().__init__(
            region="auto",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )
