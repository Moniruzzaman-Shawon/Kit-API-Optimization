# kit-media

Media handling toolkit for Python APIs — presigned URLs, chunked uploads, CDN routing, and media processing.

## Install

```bash
pip install kit-media

# With cloud provider adapters
pip install kit-media[s3]
pip install kit-media[gcs]
pip install kit-media[r2]
pip install kit-media[all]
```

## Usage

### Presigned URLs

```python
from kit_media import PresignedURLGenerator
from kit_media.adapters import S3Adapter

adapter = S3Adapter(region="us-east-1")
generator = PresignedURLGenerator(adapter=adapter)

url = await generator.generate_upload_url("my-bucket", "uploads/photo.jpg", "image/jpeg")
print(url.url, url.expires_at)
```

### Chunked Uploads

```python
from kit_media import ChunkedUploader

uploader = ChunkedUploader(adapter=adapter)
upload_id = await uploader.initiate("my-bucket", "large-file.zip", "application/zip")
etag = await uploader.upload_part(upload_id, 1, chunk_data)
location = await uploader.complete(upload_id, [(1, etag)])
```

### CDN Routing

```python
from kit_media import CDNRouter, CDNEndpoint

router = CDNRouter(endpoints=[
    CDNEndpoint(name="primary", base_url="https://cdn1.example.com", regions=["us", "eu"]),
    CDNEndpoint(name="fallback", base_url="https://cdn2.example.com", regions=["ap"]),
])

url = router.resolve("images/hero.jpg", region="us")
```
