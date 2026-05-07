"""Sliding-window rate limiter for /api/trade-analyzer.

Uses a server-side Lua script registered via redis-py's register_script().
The script is atomic (single round-trip): trims expired entries, checks the
window count, and either records the new request or returns retry-after.
In-memory fallback is per-process - used when Redis is unavailable.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Callable, Deque, Dict, Protocol, Tuple

from cache.redis_rankings import get_redis_client

logger = logging.getLogger(__name__)


_LUA = """
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
local count = redis.call('ZCARD', KEYS[1])
if count >= limit then
  local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
  return {0, math.ceil(window - (now - tonumber(oldest[2])))}
end
redis.call('ZADD', KEYS[1], now, now)
redis.call('EXPIRE', KEYS[1], window)
return {1, 0}
"""


class RateLimiter(Protocol):
    def check_and_record(self, key: str) -> Tuple[bool, int]:
        """Return (allowed, retry_after_seconds_if_denied_else_0)."""


class RedisSlidingWindowLimiter:
    def __init__(self, client, *, limit: int, window_s: int):
        self._script = client.register_script(_LUA)
        self._limit = limit
        self._window = window_s

    def check_and_record(self, key: str) -> Tuple[bool, int]:
        try:
            result = self._script(
                keys=[key],
                args=[time.time(), self._window, self._limit],
            )
        except Exception as exc:
            logger.warning("rate_limiter redis script failed, allowing: %s", exc)
            return True, 0
        allowed = bool(result[0])
        retry = int(result[1]) if not allowed else 0
        return allowed, retry


class InMemoryFallbackLimiter:
    def __init__(self, *, limit: int, window_s: int):
        self._limit = limit
        self._window = window_s
        self._buckets: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()
        self._clock: Callable[[], float] = time.monotonic

    def check_and_record(self, key: str) -> Tuple[bool, int]:
        now = self._clock()
        with self._lock:
            bucket = self._buckets.setdefault(key, deque())
            cutoff = now - self._window
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self._limit:
                retry = max(1, int(round(self._window - (now - bucket[0]))))
                return False, retry
            bucket.append(now)
            return True, 0


_INMEMORY_CACHE: Dict[Tuple[int, int], InMemoryFallbackLimiter] = {}
_INMEMORY_CACHE_LOCK = threading.Lock()


def get_rate_limiter(*, limit: int, window_s: int) -> RateLimiter:
    client = get_redis_client()
    if client is not None:
        return RedisSlidingWindowLimiter(client, limit=limit, window_s=window_s)
    cache_key = (limit, window_s)
    with _INMEMORY_CACHE_LOCK:
        cached = _INMEMORY_CACHE.get(cache_key)
        if cached is None:
            cached = InMemoryFallbackLimiter(limit=limit, window_s=window_s)
            _INMEMORY_CACHE[cache_key] = cached
        return cached
