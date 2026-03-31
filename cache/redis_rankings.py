"""
Optional Redis cache for serialized GET /api/ktc/rankings payloads.

Use when REDIS_URL is set (e.g. production multi-worker). Falls back silently
if redis is unavailable so local/dev without Redis is unchanged.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Optional
from urllib.parse import urlparse

from cache.settings import ktc_rankings_redis_ttl_seconds

logger = logging.getLogger(__name__)

_redis_lock = threading.Lock()
_RETRY_AFTER_SECONDS = 60

# None = not attempted yet; float = retry-after monotonic timestamp; else client
_redis_holder: list = [None]
_connect_log_done = False


def _redis_url_safe_summary(url: str) -> str:
    """Host/scheme/db for logs — never include password."""
    try:
        p = urlparse(url)
        host = p.hostname or ""
        port = f":{p.port}" if p.port else ""
        db = (p.path or "").lstrip("/") or "0"
        tls = p.scheme in ("rediss", "https")
        return f"scheme={p.scheme} host={host}{port} db_index={db} tls={tls}"
    except Exception:
        return "scheme=(unparsed)"


def _invalidate_after_command_error(exc: BaseException) -> None:
    """Drop cached client after transport/command failures so we reconnect after cooldown."""
    try:
        import redis

        if not isinstance(exc, redis.exceptions.RedisError):
            return
    except ImportError:
        return

    with _redis_lock:
        cached = _redis_holder[0]
        if isinstance(cached, float):
            _redis_holder[0] = time.monotonic() + _RETRY_AFTER_SECONDS
        else:
            if cached is not None:
                try:
                    cached.close()
                except Exception:
                    pass
            _redis_holder[0] = time.monotonic() + _RETRY_AFTER_SECONDS

    logger.warning(
        "Redis command failed, reconnect retry in %ss: %s",
        _RETRY_AFTER_SECONDS,
        exc,
    )


def _redis_ttl_seconds() -> int:
    return ktc_rankings_redis_ttl_seconds()


def _redis_key(is_redraft: bool, league_format: str, tep_level: str) -> str:
    tl = tep_level or ""
    return f"ktc:rankings:v1:{int(is_redraft)}:{league_format}:{tl}"


def get_redis_client():
    """Return a redis client or None if Redis should not be used."""
    global _connect_log_done
    with _redis_lock:
        cached = _redis_holder[0]
        if cached is not None:
            if isinstance(cached, float):
                if time.monotonic() < cached:
                    return None
                _redis_holder[0] = None
            else:
                return cached

        url = (os.getenv("REDIS_URL") or "").strip()
        if not url:
            return None
        try:
            import redis

            t0 = time.perf_counter()
            client = redis.from_url(
                url,
                decode_responses=False,
                socket_connect_timeout=2.5,
                socket_timeout=5.0,
            )
            client.ping()
            _redis_holder[0] = client
            if not _connect_log_done:
                _connect_log_done = True
                logger.info(
                    "Redis connected %s connect_ms=%.1f",
                    _redis_url_safe_summary(url),
                    (time.perf_counter() - t0) * 1000,
                )
            return client
        except Exception as exc:
            logger.warning(
                "Redis connect failed, retrying in %ss: %s",
                _RETRY_AFTER_SECONDS,
                exc,
            )
            _redis_holder[0] = time.monotonic() + _RETRY_AFTER_SECONDS
            return None


def redis_get_rankings_bytes(
    is_redraft: bool, league_format: str, tep_level: str
) -> Optional[bytes]:
    r = get_redis_client()
    if not r:
        return None
    key = _redis_key(is_redraft, league_format, tep_level)
    try:
        t0 = time.perf_counter()
        raw = r.get(key)
        ms = (time.perf_counter() - t0) * 1000
        if raw is None:
            logger.info("redis_rankings_get miss key=%s ms=%.1f", key, ms)
        else:
            n = len(raw) if isinstance(raw, (bytes, memoryview)) else 0
            logger.info(
                "redis_rankings_get hit key=%s bytes=%s ms=%.1f", key, n, ms
            )
        return raw
    except Exception as exc:
        _invalidate_after_command_error(exc)
        return None


def redis_set_rankings_bytes(
    is_redraft: bool,
    league_format: str,
    tep_level: str,
    payload: bytes,
    ttl_seconds: Optional[int] = None,
) -> None:
    r = get_redis_client()
    if not r:
        return
    key = _redis_key(is_redraft, league_format, tep_level)
    ttl = ttl_seconds if ttl_seconds is not None else _redis_ttl_seconds()
    try:
        t0 = time.perf_counter()
        r.setex(key, ttl, payload)
        ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "redis_rankings_set key=%s bytes=%s ttl_s=%s ms=%.1f",
            key,
            len(payload),
            ttl,
            ms,
        )
    except Exception as exc:
        _invalidate_after_command_error(exc)


def redis_invalidate_rankings(
    is_redraft: Optional[bool] = None,
    league_format: Optional[str] = None,
    tep_level: Optional[str] = None,
) -> None:
    r = get_redis_client()
    if not r:
        return
    prefix = "ktc:rankings:v1:"
    full_flush = (
        is_redraft is None
        and league_format is None
        and tep_level is None
    )
    deleted = 0
    try:
        for key in r.scan_iter(match=f"{prefix}*", count=200):
            ks = key.decode() if isinstance(key, bytes) else key
            if not ks.startswith(prefix):
                continue
            rest = ks[len(prefix) :]
            parts = rest.split(":", 2)
            if len(parts) < 3:
                continue
            ir_s, lf, tl_stored = parts[0], parts[1], parts[2]
            if not full_flush:
                if is_redraft is not None and int(ir_s) != int(is_redraft):
                    continue
                if league_format is not None and lf != league_format:
                    continue
                if tep_level is not None and tl_stored != (tep_level or ""):
                    continue
            r.delete(key)
            deleted += 1
        if deleted:
            logger.info("redis_rankings_invalidate deleted_keys=%s", deleted)
    except Exception as exc:
        _invalidate_after_command_error(exc)
