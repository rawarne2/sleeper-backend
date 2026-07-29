"""Ingest official NFL injury reports from nflverse (CC-BY-4.0, free, no API key).

nflverse publishes per-season CSV release assets. We fetch with `requests` and parse
with the stdlib `csv` module — deliberately avoiding nflreadpy/polars/pyarrow so the
serverless bundle stays light. Only the latest reported week is stored (the current
injury report is what the dashboard shows); rows resolve to players via gsis_id.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, UTC
from typing import Any, Optional

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from models.extensions import db
from models.entities import Player, PlayerInjuryReport

logger = logging.getLogger(__name__)

_INJURIES_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_{season}.csv"
)
_TIMEOUT = 60
_SOURCE = "nflverse"


def _fetch_csv(url: str) -> list[dict[str, str]]:
    resp = requests.get(url, timeout=_TIMEOUT)
    resp.raise_for_status()
    return list(csv.DictReader(io.StringIO(resp.text)))


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _clean(value: Any, limit: int) -> Optional[str]:
    text = (str(value).strip() if value is not None else "")
    if not text or text.upper() in ("NA", "NAN", "NULL"):
        return None
    return text[:limit]


def _gsis_index(session: Session) -> dict[str, int]:
    rows = session.execute(select(Player.id, Player.gsis_id)).all()
    return {gsis: pid for pid, gsis in rows if gsis}


def ingest_nflverse_injuries(season: str, *, session: Session | None = None) -> dict[str, Any]:
    """Upsert the latest-week nflverse injury report for a season into player_injury_reports."""
    session = session or db.session
    url = _INJURIES_URL.format(season=season)
    rows = _fetch_csv(url)
    weeks = [w for w in (_to_int(r.get("week")) for r in rows) if w is not None]
    if not weeks:
        return {"saved": 0, "updated": 0, "skipped": len(rows), "source_rows": len(rows), "week": None}
    max_week = max(weeks)

    gsis_index = _gsis_index(session)
    existing = {
        row.player_id: row
        for row in session.execute(
            select(PlayerInjuryReport).where(
                PlayerInjuryReport.source == _SOURCE,
                PlayerInjuryReport.season == str(season),
                PlayerInjuryReport.week == max_week,
            )
        ).scalars()
    }

    now = datetime.now(UTC)
    saved = updated = skipped = 0
    for r in rows:
        if _to_int(r.get("week")) != max_week:
            continue
        pid = gsis_index.get((r.get("gsis_id") or "").strip())
        if not pid:
            skipped += 1
            continue
        fields = dict(
            report_status=_clean(r.get("report_status"), 40),
            report_primary_injury=_clean(r.get("report_primary_injury"), 80),
            report_secondary_injury=_clean(r.get("report_secondary_injury"), 80),
            practice_status=_clean(r.get("practice_status"), 80),
            practice_primary_injury=_clean(r.get("practice_primary_injury"), 80),
        )
        row = existing.get(pid)
        if row is not None:
            for key, val in fields.items():
                setattr(row, key, val)
            row.fetched_at = now
            updated += 1
        else:
            session.add(PlayerInjuryReport(
                player_id=pid, source=_SOURCE, season=str(season), week=max_week,
                raw={}, fetched_at=now, **fields,
            ))
            saved += 1
    session.commit()
    return {"saved": saved, "updated": updated, "skipped": skipped,
            "source_rows": len(rows), "week": max_week}
