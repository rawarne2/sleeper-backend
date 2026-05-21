"""TTL cache around provider.health_check()."""
from __future__ import annotations

import time
from unittest.mock import MagicMock

from services.trade_analyzer import health_cache


def test_cached_health_check_calls_once_within_ttl(monkeypatch):
    monkeypatch.setattr(health_cache, "_TTL_SECONDS", 60.0)
    monkeypatch.setattr(health_cache, "_FAILURE_TTL_SECONDS", 5.0)
    health_cache.reset_cache()
    provider = MagicMock()
    provider.name = "gemini"
    provider.health_check.return_value = (True, "GEMINI_API_KEY present")

    a = health_cache.cached_health_check(provider)
    b = health_cache.cached_health_check(provider)

    assert a == (True, "GEMINI_API_KEY present")
    assert b == a
    assert provider.health_check.call_count == 1


def test_cached_health_check_refreshes_after_ttl(monkeypatch):
    monkeypatch.setattr(health_cache, "_TTL_SECONDS", 0.05)
    monkeypatch.setattr(health_cache, "_FAILURE_TTL_SECONDS", 0.05)
    health_cache.reset_cache()
    provider = MagicMock()
    provider.name = "gemini"
    provider.health_check.return_value = (True, "ok")

    health_cache.cached_health_check(provider)
    time.sleep(0.06)
    health_cache.cached_health_check(provider)
    assert provider.health_check.call_count == 2


def test_failures_cached_with_shorter_window(monkeypatch):
    """Failed health checks are cached briefly so a recovered provider gets noticed fast."""
    monkeypatch.setattr(health_cache, "_TTL_SECONDS", 60.0)
    monkeypatch.setattr(health_cache, "_FAILURE_TTL_SECONDS", 5.0)
    health_cache.reset_cache()
    provider = MagicMock()
    provider.name = "ollama"
    provider.health_check.return_value = (False, "ConnectionRefusedError")

    health_cache.cached_health_check(provider)
    health_cache.cached_health_check(provider)
    assert provider.health_check.call_count == 1


def test_different_providers_cached_independently(monkeypatch):
    monkeypatch.setattr(health_cache, "_TTL_SECONDS", 60.0)
    monkeypatch.setattr(health_cache, "_FAILURE_TTL_SECONDS", 5.0)
    health_cache.reset_cache()
    p1 = MagicMock(); p1.name = "gemini"
    p1.health_check.return_value = (True, "g")
    p2 = MagicMock(); p2.name = "anthropic"
    p2.health_check.return_value = (True, "a")

    health_cache.cached_health_check(p1)
    health_cache.cached_health_check(p2)
    assert p1.health_check.call_count == 1
    assert p2.health_check.call_count == 1
