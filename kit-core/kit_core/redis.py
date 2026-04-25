"""Backwards-compatible alias — re-exports from redis_client."""

from __future__ import annotations

from kit_core.redis_client import RedisClient

__all__ = ["RedisClient"]
