"""FastAPI / Starlette middleware for rate limiting and idempotency."""

from __future__ import annotations

import json
import logging
from typing import Any

from kit_core.exceptions import IdempotencyConflict, RateLimitExceeded
from kit_core.redis import RedisClient
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from kit_api.idempotency import CachedResponse, IdempotencyStore
from kit_api.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

_IDEMPOTENCY_HEADER = "idempotency-key"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class KitAPIMiddleware(BaseHTTPMiddleware):
    """Starlette-based middleware providing rate limiting and idempotency.

    Parameters
    ----------
    app:
        The ASGI application.
    redis_url:
        Redis connection URL (uses default when ``None``).
    max_requests:
        Maximum number of requests per *window_seconds*.
    window_seconds:
        Sliding window duration for rate limiting.
    idempotency_ttl:
        TTL in seconds for cached idempotent responses.
    """

    def __init__(
        self,
        app: Any,
        *,
        redis_url: str | None = None,
        max_requests: int = 100,
        window_seconds: int = 60,
        idempotency_ttl: int = 3600,
    ) -> None:
        super().__init__(app)
        redis = RedisClient(url=redis_url)
        self._rate_limiter = RateLimiter(
            redis,
            max_requests=max_requests,
            window_seconds=window_seconds,
        )
        self._idempotency_store = IdempotencyStore(redis)
        self._idempotency_ttl = idempotency_ttl

    def _client_key(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # --- Rate limiting ---
        try:
            self._rate_limiter.acquire(self._client_key(request))
        except RateLimitExceeded:
            return JSONResponse(
                {"error": "rate_limit_exceeded", "detail": "Too many requests"},
                status_code=429,
            )

        # --- Idempotency ---
        idem_key: str | None = request.headers.get(_IDEMPOTENCY_HEADER)
        if idem_key and request.method not in _SAFE_METHODS:
            cached = self._idempotency_store.check(idem_key)
            if cached is not None:
                return JSONResponse(
                    cached.body,
                    status_code=cached.status_code,
                    headers=cached.headers,
                )
            try:
                self._idempotency_store.acquire_lock(idem_key)
            except IdempotencyConflict:
                return JSONResponse(
                    {"error": "idempotency_conflict", "detail": "Duplicate request in progress"},
                    status_code=409,
                )

        response: Response = await call_next(request)

        # Store response for idempotent requests.
        if idem_key and request.method not in _SAFE_METHODS:
            body_bytes = b""
            async for chunk in response.body_iterator:  # type: ignore[attr-defined]
                body_bytes += chunk if isinstance(chunk, bytes) else chunk.encode()

            try:
                body_data = json.loads(body_bytes)
            except Exception:
                body_data = body_bytes.decode("utf-8", errors="replace")

            cached_resp = CachedResponse(
                status_code=response.status_code,
                body=body_data,
                headers=dict(response.headers),
            )
            self._idempotency_store.store(idem_key, cached_resp, ttl=self._idempotency_ttl)
            self._idempotency_store.release_lock(idem_key)

            # Rebuild response since body_iterator was consumed.
            response = Response(
                content=body_bytes,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        remaining = self._rate_limiter.remaining(self._client_key(request))
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
