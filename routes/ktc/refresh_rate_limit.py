"""Rate limiting for the expensive KTC refresh endpoints.

A full KTC scrape takes minutes; left unprotected, the public ``POST /api/ktc/refresh``
and ``POST /api/ktc/refresh/all`` routes can be hammered into repeated multi-minute
scrapes. This reuses the sliding-window limiter built for the trade analyzer
(``cache/rate_limiter.py`` — Redis with an in-memory fallback) rather than adding a
new dependency.

The scheduled nightly cron does **not** hit these HTTP routes (it calls
``scrape_and_save_all_ktc_data`` directly via ``services/daily_refresh.py``), so this
only throttles ad-hoc/abusive callers.
"""
from __future__ import annotations

import os
from typing import Optional, Tuple

from flask import Response, request

from cache.rate_limiter import get_rate_limiter
from routes.helpers import json_api_error


def _client_ip() -> str:
    return (request.headers.get("X-Forwarded-For")
            or request.remote_addr or "0.0.0.0").split(",")[0].strip()


def _enabled() -> bool:
    return (os.getenv("KTC_REFRESH_RATE_LIMIT_ENABLED", "true").strip().lower()
            not in ("0", "false", "no"))


def ktc_refresh_rate_limited() -> Optional[Tuple[Response, int]]:
    """Return a 429 ``json_api_error`` response if the caller is over budget, else None."""
    if not _enabled():
        return None

    limiter = get_rate_limiter(
        limit=int(os.getenv("KTC_REFRESH_RATE_LIMIT_PER_WINDOW", "20")),
        window_s=int(os.getenv("KTC_REFRESH_RATE_LIMIT_WINDOW_SECONDS", "300")),
    )
    allowed, retry_after = limiter.check_and_record(
        f"ktc_refresh:rl:v1:ip:{_client_ip()}")
    if not allowed:
        return json_api_error(
            "Rate limit exceeded", 429,
            details=f"KTC refresh is expensive; try again in {retry_after} seconds",
            retry_after_seconds=retry_after,
        )
    return None
