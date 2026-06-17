"""
Redis cache for serialized GET /api/players/all payloads.

The full player universe only changes on a KTC refresh (and is invalidated
there), so a long TTL is safe. Reuses the connection management in
``cache.redis_rankings`` so there is a single Redis client per worker.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from cache.redis_rankings import (
    RedisConfigurationError,
    _invalidate_after_command_error,
    _redis_mandatory,
    get_redis_client,
)
from cache.settings import players_all_redis_ttl_seconds

logger = logging.getLogger(__name__)

_PREFIX = "players:all:v2:"


def _redis_key(
    is_redraft: bool, league_format: str, tep_level: str, season: str,
    league_id: str = "",
) -> str:
    return (
        f"{_PREFIX}{int(is_redraft)}:{league_format}:{tep_level or ''}:"
        f"{season or ''}:{league_id or ''}"
    )


def redis_get_players_all_bytes(
    is_redraft: bool, league_format: str, tep_level: str, season: str,
    league_id: str = "",
) -> Optional[bytes]:
    r = get_redis_client()
    if not r:
        return None
    key = _redis_key(is_redraft, league_format, tep_level, season, league_id)
    try:
        t0 = time.perf_counter()
        raw = r.get(key)
        ms = (time.perf_counter() - t0) * 1000
        if raw is None:
            logger.info("redis_players_all_get miss key=%s ms=%.1f", key, ms)
        else:
            n = len(raw) if isinstance(raw, (bytes, memoryview)) else 0
            logger.info("redis_players_all_get hit key=%s bytes=%s ms=%.1f", key, n, ms)
        return raw
    except Exception as exc:
        _invalidate_after_command_error(exc)
        if _redis_mandatory():
            raise RedisConfigurationError("Redis players-all read failed in production") from exc
        return None


def redis_set_players_all_bytes(
    is_redraft: bool,
    league_format: str,
    tep_level: str,
    season: str,
    payload: bytes,
    ttl_seconds: Optional[int] = None,
    league_id: str = "",
) -> None:
    r = get_redis_client()
    if not r:
        return
    key = _redis_key(is_redraft, league_format, tep_level, season, league_id)
    ttl = ttl_seconds if ttl_seconds is not None else players_all_redis_ttl_seconds()
    try:
        t0 = time.perf_counter()
        r.setex(key, ttl, payload)
        ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "redis_players_all_set key=%s bytes=%s ttl_s=%s ms=%.1f",
            key, len(payload), ttl, ms,
        )
    except Exception as exc:
        _invalidate_after_command_error(exc)
        if _redis_mandatory():
            raise RedisConfigurationError("Redis players-all write failed in production") from exc


def redis_invalidate_players_all() -> None:
    """Drop every cached players-all payload (call on KTC refresh)."""
    try:
        r = get_redis_client()
    except RedisConfigurationError as exc:
        logger.warning("redis_players_all_invalidate skipped: %s", exc)
        return
    if not r:
        return
    deleted = 0
    try:
        for key in r.scan_iter(match=f"{_PREFIX}*", count=200):
            r.delete(key)
            deleted += 1
        if deleted:
            logger.info("redis_players_all_invalidate deleted_keys=%s", deleted)
    except Exception as exc:
        _invalidate_after_command_error(exc)
        if _redis_mandatory():
            logger.error("redis_players_all_invalidate failed in production: %s", exc)
