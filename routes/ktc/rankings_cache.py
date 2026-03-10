"""
In-process cache for GET /api/ktc/rankings responses.

The external KTC API cannot be sped up; refresh already persists to the DB.
GET was still slow because every request:
  1) Loaded all players from DB with joins
  2) Ran filter_players_by_format with deepcopy per player
  3) Serialized a large JSON payload

Caching the serialized JSON avoids repeating that work. TTL bounds staleness;
refresh/cleanup endpoints invalidate so updates are visible immediately.

For serverless/multi-worker, each instance has its own cache; pair with
Cache-Control headers so CDN/browser can cache too.
"""
import json
import threading
import time
from typing import Optional, Tuple

# Default TTL: repeat hits skip DB+filter work. Refresh/cleanup/bulk clear
# the cache, so a longer TTL is safe and improves initial load on warm workers.
_DEFAULT_TTL_SECONDS = 3600

_lock = threading.Lock()
# key -> (expires_at_epoch, json_bytes)
_cache: dict[tuple, tuple[float, bytes]] = {}


def _cache_key(is_redraft: bool, league_format: str, tep_level: str) -> tuple:
    return (is_redraft, league_format, tep_level or "")


def get_cached_rankings_json(
    is_redraft: bool, league_format: str, tep_level: str
) -> Optional[bytes]:
    """Return cached JSON bytes if present and not expired."""
    key = _cache_key(is_redraft, league_format, tep_level)
    now = time.monotonic()
    with _lock:
        entry = _cache.get(key)
        if not entry:
            return None
        expires_at, payload = entry
        if now >= expires_at:
            del _cache[key]
            return None
        return payload


def set_cached_rankings_json(
    is_redraft: bool,
    league_format: str,
    tep_level: str,
    payload: dict,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
) -> bytes:
    """Serialize payload, store under key, return json bytes."""
    json_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    key = _cache_key(is_redraft, league_format, tep_level)
    expires_at = time.monotonic() + ttl_seconds
    with _lock:
        _cache[key] = (expires_at, json_bytes)
    return json_bytes


def invalidate_rankings_cache(
    is_redraft: Optional[bool] = None,
    league_format: Optional[str] = None,
    tep_level: Optional[str] = None,
) -> None:
    """
    Invalidate cache entries. If all args None, clear entire cache.
    Otherwise remove keys matching the given dimensions (None = wildcard).
    """
    with _lock:
        if is_redraft is None and league_format is None and tep_level is None:
            _cache.clear()
            return
        tep_norm = tep_level if tep_level is not None else None
        keys_to_delete = []
        for key in _cache:
            ir, lf, tl = key
            if is_redraft is not None and ir != is_redraft:
                continue
            if league_format is not None and lf != league_format:
                continue
            if tep_norm is not None and tl != (tep_norm or ""):
                continue
            keys_to_delete.append(key)
        for k in keys_to_delete:
            _cache.pop(k, None)


def cache_stats() -> Tuple[int, int]:
    """Return (entry_count, total_payload_bytes) for observability."""
    with _lock:
        n = len(_cache)
        total = sum(len(v[1]) for v in _cache.values())
    return n, total
