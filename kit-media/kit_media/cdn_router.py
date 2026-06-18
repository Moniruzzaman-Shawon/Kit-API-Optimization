from __future__ import annotations

import hashlib
import hmac
import random
import time
from dataclasses import dataclass, field

import httpx
from kit_core import get_logger

logger = get_logger(__name__)


@dataclass
class CDNEndpoint:
    """A CDN endpoint with region affinity and weight."""

    name: str
    base_url: str
    regions: list[str] = field(default_factory=list)
    weight: int = 1
    signing_key: str | None = None
    purge_api: str | None = None
    purge_headers: dict[str, str] = field(default_factory=dict)


class CDNRouter:
    """Routes requests to the best CDN endpoint based on region and weight."""

    def __init__(self, endpoints: list[CDNEndpoint]) -> None:
        if not endpoints:
            raise ValueError("At least one CDN endpoint is required")
        self._endpoints = endpoints
        self._client = httpx.AsyncClient(timeout=10)

    def resolve(self, key: str, region: str | None = None) -> str:
        """Resolve the best CDN URL for the given object key and optional region.

        If a region is provided, endpoints matching that region are preferred.
        Among matching endpoints, one is chosen randomly weighted by `weight`.
        """
        candidates = self._endpoints
        if region:
            regional = [
                ep for ep in candidates
                if region.lower() in [r.lower() for r in ep.regions]
            ]
            if regional:
                candidates = regional

        endpoint = self._weighted_choice(candidates)
        base = endpoint.base_url.rstrip("/")
        url = f"{base}/{key.lstrip('/')}"

        if endpoint.signing_key:
            url = self._sign_url(url, endpoint.signing_key)

        return url

    def resolve_all(self, key: str) -> list[str]:
        """Return URLs from all endpoints for the given key."""
        urls = []
        for ep in self._endpoints:
            base = ep.base_url.rstrip("/")
            url = f"{base}/{key.lstrip('/')}"
            if ep.signing_key:
                url = self._sign_url(url, ep.signing_key)
            urls.append(url)
        return urls

    async def purge(self, key: str) -> None:
        """Purge a single key from all CDN endpoints that support purging."""
        for ep in self._endpoints:
            if ep.purge_api:
                await self._send_purge(ep, [key])

    async def purge_prefix(self, prefix: str) -> None:
        """Purge all objects matching a prefix from all CDN endpoints."""
        for ep in self._endpoints:
            if ep.purge_api:
                await self._send_purge(ep, [f"{prefix}*"])

    async def _send_purge(self, endpoint: CDNEndpoint, paths: list[str]) -> None:
        try:
            resp = await self._client.post(
                endpoint.purge_api,  # type: ignore[arg-type]
                json={"files": paths},
                headers=endpoint.purge_headers,
            )
            resp.raise_for_status()
            logger.info("cdn_purge_sent", endpoint=endpoint.name, paths=paths)
        except httpx.HTTPError as exc:
            logger.error("cdn_purge_failed", endpoint=endpoint.name, error=str(exc))

    @staticmethod
    def _weighted_choice(endpoints: list[CDNEndpoint]) -> CDNEndpoint:
        total = sum(ep.weight for ep in endpoints)
        r = random.randint(1, total)
        cumulative = 0
        for ep in endpoints:
            cumulative += ep.weight
            if r <= cumulative:
                return ep
        return endpoints[-1]

    @staticmethod
    def _sign_url(url: str, key: str, ttl: int = 3600) -> str:
        expires = int(time.time()) + ttl
        to_sign = f"{url}?expires={expires}"
        signature = hmac.new(
            key.encode(),
            to_sign.encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"{url}?expires={expires}&sig={signature}"

    async def close(self) -> None:
        await self._client.aclose()
