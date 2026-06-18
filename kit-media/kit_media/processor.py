from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlencode


class FitMode(str, Enum):
    COVER = "cover"
    CONTAIN = "contain"
    FILL = "fill"


ALLOWED_MEDIA_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/avif",
    "image/gif",
    "image/svg+xml",
    "video/mp4",
    "video/webm",
    "video/quicktime",
    "audio/mpeg",
    "audio/ogg",
    "audio/wav",
    "application/pdf",
}


@dataclass
class TransformSpec:
    """Specification for an image/video transformation."""

    width: int | None = None
    height: int | None = None
    format: str | None = None
    quality: int | None = None
    fit: FitMode = FitMode.COVER

    def to_params(self) -> dict[str, str]:
        params: dict[str, str] = {}
        if self.width:
            params["w"] = str(self.width)
        if self.height:
            params["h"] = str(self.height)
        if self.format:
            params["fm"] = self.format
        if self.quality:
            params["q"] = str(self.quality)
        params["fit"] = self.fit.value
        return params


class MediaProcessor:
    """Builds CDN transformation URLs and validates media types."""

    def __init__(self, transform_base_url: str | None = None) -> None:
        self._transform_base = transform_base_url

    def build_transform_url(self, source_url: str, spec: TransformSpec) -> str:
        """Build a CDN transformation URL from a source URL and transform spec.

        If a transform_base_url is configured, the source is passed as an
        origin parameter. Otherwise, transform params are appended to the
        source URL directly.
        """
        params = spec.to_params()

        if self._transform_base:
            params["url"] = source_url
            base = self._transform_base.rstrip("/")
            return f"{base}/?{urlencode(params)}"

        separator = "&" if "?" in source_url else "?"
        return f"{source_url}{separator}{urlencode(params)}"

    @staticmethod
    def validate_media_type(content_type: str) -> bool:
        """Check if a MIME type is in the allowed media types set."""
        return content_type.lower().strip() in ALLOWED_MEDIA_TYPES

    @staticmethod
    def get_dimensions(file_path: str) -> tuple[int, int]:
        """Get image dimensions using Pillow (must be installed separately).

        Returns:
            Tuple of (width, height).

        Raises:
            ImportError: If Pillow is not installed.
            MediaError: If the file cannot be read.
        """
        try:
            from PIL import Image
        except ImportError:
            raise ImportError(
                "Pillow is required for get_dimensions(). "
                "Install it with: pip install Pillow"
            ) from None

        from kit_core.exceptions import MediaError

        try:
            with Image.open(file_path) as img:
                return img.size
        except Exception as exc:
            raise MediaError(f"Failed to read image dimensions: {exc}") from exc
