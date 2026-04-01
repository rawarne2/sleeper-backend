"""Tests for RFC 3339 UTC serialization."""
from datetime import UTC, datetime, timedelta, timezone

from utils.datetime_serialization import format_instant_rfc3339_utc, utc_now_rfc3339


def test_none():
    assert format_instant_rfc3339_utc(None) is None


def test_naive_treated_as_utc():
    dt = datetime(2026, 3, 31, 18, 30, 0)
    assert format_instant_rfc3339_utc(dt) == "2026-03-31T18:30:00Z"


def test_aware_utc_uses_z():
    dt = datetime(2026, 3, 31, 18, 30, 0, tzinfo=UTC)
    assert format_instant_rfc3339_utc(dt) == "2026-03-31T18:30:00Z"


def test_non_utc_converted():
    eastern = timezone(timedelta(hours=-4))
    dt = datetime(2026, 3, 31, 14, 30, 0, tzinfo=eastern)
    assert format_instant_rfc3339_utc(dt) == "2026-03-31T18:30:00Z"


def test_microseconds_trimmed_by_isoformat():
    dt = datetime(2026, 3, 31, 18, 30, 0, 123000, tzinfo=UTC)
    out = format_instant_rfc3339_utc(dt)
    assert out.endswith("Z")
    assert "18:30:00" in out


def test_utc_now_non_empty():
    s = utc_now_rfc3339()
    assert s.endswith("Z")
    assert "T" in s
