"""
Redis cache for GET /api/dashboard/league/:id JSON responses.

Cache key (v1, all segments from normalized query params):

  dashboard:league:v1:{league_id}:{season}:{league_format}:{tep_level}:{is_redraft}

``tep_level`` is empty string when omitted. ``is_redraft`` is 0 or 1.
Invalidation: per-league via ``invalidate_dashboard_league``; KTC ranking
invalidation also clears matching dashboard keys (see
``invalidate_dashboard_league_caches_for_ktc_dimensions``).

Required on Vercel production together with REDIS_URL; see cache.redis_rankings.
"""
from __future__ import annotations

import logging
from typing import Optional

from cache.redis_rankings import (
    RedisConfigurationError,
    get_redis_client,
    _invalidate_after_command_error,
    _redis_mandatory,
)
from cache.settings import dashboard_league_redis_ttl_seconds

logger = logging.getLogger(__name__)

_PREFIX = "dashboard:league:v1:"


def dashboard_league_cache_key(
    league_id: str,
    season: str,
    league_format: str,
    tep_level: str,
    is_redraft: bool,
) -> str:
    tl = tep_level or ""
    return f"{_PREFIX}{league_id}:{season}:{league_format}:{tl}:{int(is_redraft)}"


def redis_get_dashboard_league_bytes(key: str) -> Optional[bytes]:
    r = get_redis_client()
    if not r:
        return None
    try:
        return r.get(key)
    except Exception as exc:
        _invalidate_after_command_error(exc)
        if _redis_mandatory():
            raise RedisConfigurationError(
                "Redis dashboard read failed in production"
            ) from exc
        return None


def redis_set_dashboard_league_bytes(key: str, payload: bytes) -> None:
    r = get_redis_client()
    if not r:
        return
    ttl = dashboard_league_redis_ttl_seconds()
    try:
        r.setex(key, ttl, payload)
        logger.debug(
            "redis_dashboard_set key=%s bytes=%s ttl_s=%s",
            key,
            len(payload),
            ttl,
        )
    except Exception as exc:
        _invalidate_after_command_error(exc)
        if _redis_mandatory():
            raise RedisConfigurationError(
                "Redis dashboard write failed in production"
            ) from exc


def invalidate_dashboard_league_caches_for_ktc_dimensions(
    is_redraft: Optional[bool] = None,
    league_format: Optional[str] = None,
    tep_level: Optional[str] = None,
) -> None:
    """
    Drop dashboard bundle keys affected by a KTC rankings invalidation.

    Key tail matches ``...:{league_id}:{season}:{league_format}:{tep}:{is_redraft}``.
    ``None`` for a dimension means wildcard (same semantics as rankings Redis).
    """
    try:
        r = get_redis_client()
    except RedisConfigurationError as exc:
        logger.warning("redis_dashboard_ktc_invalidate skipped: %s", exc)
        return
    if not r:
        return
    full_flush = (
        is_redraft is None
        and league_format is None
        and tep_level is None
    )
    tep_cmp = tep_level if tep_level is not None else None
    deleted = 0
    try:
        for key in r.scan_iter(match=f"{_PREFIX}*", count=200):
            ks = key.decode() if isinstance(key, bytes) else key
            if not ks.startswith(_PREFIX):
                continue
            parts = ks.split(":")
            if len(parts) < 8:
                continue
            lf, tl_stored, ir_s = parts[5], parts[6], parts[7]
            if not full_flush:
                if is_redraft is not None and int(ir_s) != int(is_redraft):
                    continue
                if league_format is not None and lf != league_format:
                    continue
                if tep_cmp is not None and tl_stored != (tep_cmp or ""):
                    continue
            r.delete(key)
            deleted += 1
        if deleted:
            logger.info(
                "redis_dashboard_ktc_invalidate deleted_keys=%s", deleted
            )
    except Exception as exc:
        _invalidate_after_command_error(exc)
        if _redis_mandatory():
            logger.error(
                "redis_dashboard_ktc_invalidate failed in production: %s", exc
            )


def invalidate_dashboard_league(league_id: str) -> None:
    """Drop cached dashboard bundles for one league (all season/format variants)."""
    try:
        r = get_redis_client()
    except RedisConfigurationError as exc:
        logger.warning("redis_dashboard_invalidate skipped: %s", exc)
        return
    if not r:
        return
    pattern = f"{_PREFIX}{league_id}:*"
    deleted = 0
    try:
        for key in r.scan_iter(match=pattern, count=200):
            r.delete(key)
            deleted += 1
        if deleted:
            logger.info(
                "redis_dashboard_invalidate league_id=%s deleted_keys=%s",
                league_id,
                deleted,
            )
    except Exception as exc:
        _invalidate_after_command_error(exc)
        if _redis_mandatory():
            logger.error(
                "redis_dashboard_invalidate failed in production: %s", exc
            )
