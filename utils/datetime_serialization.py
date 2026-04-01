"""Serialize aware/naive datetimes as RFC 3339 instants with explicit UTC (Z)."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional


def format_instant_rfc3339_utc(dt: Optional[datetime]) -> Optional[str]:
    """
    Format a wall-clock instant for JSON APIs.

    Naive datetimes are interpreted as UTC (Postgres timestamptz often loads as naive UTC).
    Aware datetimes are converted to UTC. Output uses a Z suffix (not +00:00).
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)
    s = dt.isoformat()
    if s.endswith("+00:00"):
        return s[:-6] + "Z"
    return s


def utc_now_rfc3339() -> str:
    """Current UTC instant; always non-null."""
    out = format_instant_rfc3339_utc(datetime.now(UTC))
    assert out is not None
    return out
