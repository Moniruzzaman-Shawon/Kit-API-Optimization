"""Tests for kit_media.processor — no external dependencies needed."""

from __future__ import annotations

from kit_media.processor import FitMode, MediaProcessor, TransformSpec


class TestTransformSpec:
    def test_to_params_full(self):
        spec = TransformSpec(width=800, height=600, format="webp", quality=80, fit=FitMode.CONTAIN)
        params = spec.to_params()
        assert params == {"w": "800", "h": "600", "fm": "webp", "q": "80", "fit": "contain"}

    def test_to_params_minimal(self):
        spec = TransformSpec()
        params = spec.to_params()
        assert params == {"fit": "cover"}

    def test_to_params_partial(self):
        spec = TransformSpec(width=400)
        params = spec.to_params()
        assert params == {"w": "400", "fit": "cover"}


class TestMediaProcessor:
    def test_build_transform_url_appends_params(self):
        processor = MediaProcessor()
        spec = TransformSpec(width=200, height=200, format="webp")
        url = processor.build_transform_url("https://cdn.example.com/img.jpg", spec)
        assert "https://cdn.example.com/img.jpg?" in url
        assert "w=200" in url
        assert "h=200" in url
        assert "fm=webp" in url

    def test_build_transform_url_with_existing_query(self):
        processor = MediaProcessor()
        spec = TransformSpec(width=100)
        url = processor.build_transform_url("https://cdn.example.com/img.jpg?token=abc", spec)
        assert "https://cdn.example.com/img.jpg?token=abc&" in url
        assert "w=100" in url

    def test_build_transform_url_with_base(self):
        processor = MediaProcessor(transform_base_url="https://transform.example.com")
        spec = TransformSpec(width=300)
        url = processor.build_transform_url("https://cdn.example.com/img.jpg", spec)
        assert url.startswith("https://transform.example.com/")
        assert "url=https" in url
        assert "w=300" in url

    def test_validate_media_type_valid(self):
        assert MediaProcessor.validate_media_type("image/jpeg") is True
        assert MediaProcessor.validate_media_type("video/mp4") is True
        assert MediaProcessor.validate_media_type("audio/mpeg") is True
        assert MediaProcessor.validate_media_type("application/pdf") is True

    def test_validate_media_type_invalid(self):
        assert MediaProcessor.validate_media_type("application/json") is False
        assert MediaProcessor.validate_media_type("text/html") is False

    def test_validate_media_type_case_insensitive(self):
        assert MediaProcessor.validate_media_type("Image/JPEG") is True
        assert MediaProcessor.validate_media_type(" image/png ") is True
