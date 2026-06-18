"""Tests for kit_media.cdn_router — no external dependencies needed."""

from __future__ import annotations

import pytest
from kit_media.cdn_router import CDNEndpoint, CDNRouter


@pytest.fixture
def router():
    return CDNRouter(
        endpoints=[
            CDNEndpoint(
                name="us-cdn", base_url="https://us.cdn.example.com",
                regions=["us", "ca"], weight=2,
            ),
            CDNEndpoint(
                name="eu-cdn", base_url="https://eu.cdn.example.com",
                regions=["eu", "uk"], weight=1,
            ),
            CDNEndpoint(
                name="ap-cdn", base_url="https://ap.cdn.example.com",
                regions=["ap", "jp"], weight=1,
            ),
        ]
    )


class TestCDNRouter:
    def test_requires_at_least_one_endpoint(self):
        with pytest.raises(ValueError, match="(?i)at least one"):
            CDNRouter(endpoints=[])

    def test_resolve_returns_url(self, router):
        url = router.resolve("images/hero.jpg")
        assert "images/hero.jpg" in url
        assert url.startswith("https://")

    def test_resolve_prefers_matching_region(self, router):
        # Run multiple times to verify region preference
        for _ in range(10):
            url = router.resolve("img.jpg", region="eu")
            assert "eu.cdn.example.com" in url

    def test_resolve_falls_back_to_any_when_no_region_match(self, router):
        url = router.resolve("img.jpg", region="unknown-region")
        assert url.startswith("https://")
        assert "img.jpg" in url

    def test_resolve_all(self, router):
        urls = router.resolve_all("file.txt")
        assert len(urls) == 3
        bases = [u.split("/file.txt")[0] for u in urls]
        assert "https://us.cdn.example.com" in bases
        assert "https://eu.cdn.example.com" in bases
        assert "https://ap.cdn.example.com" in bases

    def test_signed_url(self):
        router = CDNRouter(
            endpoints=[
                CDNEndpoint(
                    name="signed",
                    base_url="https://secure.cdn.example.com",
                    signing_key="secret123",
                ),
            ]
        )
        url = router.resolve("private/doc.pdf")
        assert "expires=" in url
        assert "sig=" in url


class TestCDNEndpoint:
    def test_dataclass_defaults(self):
        ep = CDNEndpoint(name="test", base_url="https://test.com")
        assert ep.regions == []
        assert ep.weight == 1
        assert ep.signing_key is None
