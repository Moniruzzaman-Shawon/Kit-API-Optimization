"""Django middleware for rate limiting and idempotency enforcement."""

from __future__ import annotations

import logging
from typing import Any, Callable

from django.http import HttpRequest, HttpResponse, JsonResponse

from kit_core.exceptions import IdempotencyConflict, RateLimitExceeded
from kit_core.redis import RedisClient

from kit_api.idempotency import IdempotencyStore
from kit_api.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

_IDEMPOTENCY_HEADER = "Idempotency-Key"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class KitAPIMiddleware:
    """Django middleware that applies rate limiting and idempotency checks.

    Configuration is read from ``django.conf.settings``:

    * ``KIT_API_RATE_LIMIT_MAX`` -- max requests per window (default 100)
    * ``KIT_API_RATE_LIMIT_WINDOW`` -- window in seconds (default 60)
    * ``KIT_API_IDEMPOTENCY_TTL`` -- cached response TTL (default 3600)
    * ``KIT_API_REDIS_URL`` -- Redis connection URL (optional, uses default)
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self._configure()

    def _configure(self) -> None:
        from django.conf import settings

        redis = RedisClient(url=getattr(settings, "KIT_API_REDIS_URL", None))
        max_requests: int = getattr(settings, "KIT_API_RATE_LIMIT_MAX", 100)
        window: int = getattr(settings, "KIT_API_RATE_LIMIT_WINDOW", 60)
        self._idempotency_ttl: int = getattr(settings, "KIT_API_IDEMPOTENCY_TTL", 3600)

        self._rate_limiter = RateLimiter(
            redis,
            max_requests=max_requests,
            window_seconds=window,
        )
        self._idempotency_store = IdempotencyStore(redis)

    def _client_key(self, request: HttpRequest) -> str:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "unknown")

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # --- Rate limiting ---
        try:
            self._rate_limiter.acquire(self._client_key(request))
        except RateLimitExceeded:
            return JsonResponse(
                {"error": "rate_limit_exceeded", "detail": "Too many requests"},
                status=429,
            )

        # --- Idempotency (non-safe methods only) ---
        idem_key: str | None = request.headers.get(_IDEMPOTENCY_HEADER)
        if idem_key and request.method not in _SAFE_METHODS:
            cached = self._idempotency_store.check(idem_key)
            if cached is not None:
                return JsonResponse(
                    cached.body,
                    status=cached.status_code,
                    headers=cached.headers,
                )
            try:
                self._idempotency_store.acquire_lock(idem_key)
            except IdempotencyConflict:
                return JsonResponse(
                    {"error": "idempotency_conflict", "detail": "Duplicate request in progress"},
                    status=409,
                )

        response: HttpResponse = self.get_response(request)

        # Store response for idempotent requests.
        if idem_key and request.method not in _SAFE_METHODS:
            from kit_api.idempotency import CachedResponse

            cached_resp = CachedResponse(
                status_code=response.status_code,
                body=self._safe_body(response),
                headers=dict(response.headers),
            )
            self._idempotency_store.store(idem_key, cached_resp, ttl=self._idempotency_ttl)
            self._idempotency_store.release_lock(idem_key)

        remaining = self._rate_limiter.remaining(self._client_key(request))
        response["X-RateLimit-Remaining"] = str(remaining)
        return response

    @staticmethod
    def _safe_body(response: HttpResponse) -> Any:
        try:
            import json
            return json.loads(response.content)
        except Exception:
            return response.content.decode("utf-8", errors="replace")
