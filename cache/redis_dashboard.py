"""
Optional Redis cache for GET /api/dashboard/league/:id JSON responses.

Short TTL keeps repeated dashboard loads fast under multi-worker deploys while
letting KTC/research updates appear within ~minutes without per-key invalidation.
Invalidate explicitly after a Sleeper league snapshot refresh.
"""
from __future__ import annotations

import logging
from typing import Optional

from cache.redis_rankings import get_redis_client, _invalidate_after_command_error
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


def invalidate_dashboard_league(league_id: str) -> None:
    """Drop cached dashboard bundles for one league (all season/format variants)."""
    r = get_redis_client()
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
