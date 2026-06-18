# kit-media — Media handling

Tools for direct-to-cloud uploads, CDN delivery, and media processing — so large files never
proxy through your app server.

**Install:** `pip install kit-media` (storage adapters: `kit-media[s3]`, `kit-media[gcs]`, `kit-media[r2]`, or `kit-media[all]`)

← Back to [docs index](index.md) · Problem-oriented walkthrough in the [Usage Guide](guide.md) ·
Full reference in the [README](../README.md)

## Components

| Component | Solves |
|-----------|--------|
| `PresignedURLGenerator` | Secure, time-limited direct upload/download URLs (S3/R2/GCS) |
| `ChunkedUploader` | Resumable multipart uploads with progress tracked in Redis |
| `CDNRouter` / `CDNEndpoint` | Region-aware, weighted CDN routing; signed URLs; cache purge |
| `MediaProcessor` | Build CDN transform URLs; validate MIME types; image dimensions |
| `CaptionJob` | Manage async transcription/captioning jobs with Redis state |

All are importable from the top-level package, e.g. `from kit_media import CDNRouter, CDNEndpoint`.

## Minimal example

```python
from kit_media import PresignedURLGenerator
from kit_media.adapters.s3_adapter import S3Adapter

gen = PresignedURLGenerator(adapter=S3Adapter(region="us-east-1"))
upload = await gen.generate_upload_url(
    bucket="my-bucket", key="uploads/photo.jpg", content_type="image/jpeg", expires=3600,
)
```

## Storage adapters

`from kit_media.adapters.s3_adapter import S3Adapter` · `r2_adapter.R2Adapter` ·
`gcs_adapter.GCSAdapter`. Install the matching extra so the underlying SDK is present.

See the [README](../README.md#package-2-kit-media--media-handling) for full parameters and the
chunked-upload / CDN / processor APIs.
