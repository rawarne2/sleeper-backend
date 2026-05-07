"""Sliding-window rate limiter tests."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cache.rate_limiter import (
    InMemoryFallbackLimiter,
    RedisSlidingWindowLimiter,
    get_rate_limiter,
)


def test_inmemory_allows_under_limit():
    lim = InMemoryFallbackLimiter(limit=3, window_s=60)
    for _ in range(3):
        allowed, retry = lim.check_and_record("key")
        assert allowed is True
        assert retry == 0


def test_inmemory_denies_over_limit():
    lim = InMemoryFallbackLimiter(limit=2, window_s=60)
    lim.check_and_record("key")
    lim.check_and_record("key")
    allowed, retry = lim.check_and_record("key")
    assert allowed is False
    assert retry > 0


def test_inmemory_window_expires():
    lim = InMemoryFallbackLimiter(limit=1, window_s=60)
    fake_now = [1000.0]
    lim._clock = lambda: fake_now[0]
    lim.check_and_record("key")
    allowed, _ = lim.check_and_record("key")
    assert allowed is False
    fake_now[0] += 61
    allowed, _ = lim.check_and_record("key")
    assert allowed is True


def test_inmemory_keys_independent():
    lim = InMemoryFallbackLimiter(limit=1, window_s=60)
    lim.check_and_record("a")
    allowed, _ = lim.check_and_record("b")
    assert allowed is True


def test_redis_limiter_allows_when_script_returns_one():
    fake_client = MagicMock()
    fake_script = MagicMock(return_value=[1, 0])
    fake_client.register_script.return_value = fake_script
    lim = RedisSlidingWindowLimiter(fake_client, limit=3, window_s=60)
    allowed, retry = lim.check_and_record("k")
    assert allowed is True
    assert retry == 0
    assert fake_script.call_count == 1


def test_redis_limiter_denies_when_script_returns_zero():
    fake_client = MagicMock()
    fake_script = MagicMock(return_value=[0, 42])
    fake_client.register_script.return_value = fake_script
    lim = RedisSlidingWindowLimiter(fake_client, limit=3, window_s=60)
    allowed, retry = lim.check_and_record("k")
    assert allowed is False
    assert retry == 42


def test_redis_limiter_falls_back_on_redis_error():
    fake_client = MagicMock()
    fake_script = MagicMock(side_effect=RuntimeError("redis down"))
    fake_client.register_script.return_value = fake_script
    lim = RedisSlidingWindowLimiter(fake_client, limit=3, window_s=60)
    allowed, retry = lim.check_and_record("k")
    assert allowed is True
    assert retry == 0


def test_get_rate_limiter_returns_redis_when_available():
    sentinel = MagicMock()
    sentinel.register_script.return_value = MagicMock(return_value=[1, 0])
    with patch("cache.rate_limiter.get_redis_client", return_value=sentinel):
        lim = get_rate_limiter(limit=5, window_s=60)
    assert isinstance(lim, RedisSlidingWindowLimiter)


def test_get_rate_limiter_returns_inmemory_when_redis_missing():
    with patch("cache.rate_limiter.get_redis_client", return_value=None):
        lim = get_rate_limiter(limit=5, window_s=60)
    assert isinstance(lim, InMemoryFallbackLimiter)
