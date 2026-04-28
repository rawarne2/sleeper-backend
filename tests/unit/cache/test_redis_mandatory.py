"""Production Redis requirements (VERCEL_ENV=production)."""

import pytest

import cache.redis_rankings as redis_rankings_mod
from cache.redis_rankings import RedisConfigurationError, get_redis_client


@pytest.fixture(autouse=True)
def _reset_redis_holder():
    with redis_rankings_mod._redis_lock:
        old = redis_rankings_mod._redis_holder[0]
        redis_rankings_mod._redis_holder[0] = None
    if old is not None and not isinstance(old, float):
        try:
            old.close()
        except Exception:
            pass
    redis_rankings_mod._connect_log_done = False
    yield


def test_production_requires_redis_url(monkeypatch):
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.delenv("REDIS_URL", raising=False)
    with pytest.raises(RedisConfigurationError, match="REDIS_URL"):
        get_redis_client()


def test_non_production_allows_missing_redis_url(monkeypatch):
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    assert get_redis_client() is None
