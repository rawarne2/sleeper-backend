"""Curated data-source attribution registry, exposed on API bundles for the UI credits.

One entry per external source the app uses, with the human credit + any license/usage
obligation. Enriched with last_synced_at from the value_sources table where available.
"""
from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.extensions import db
from models.entities import ValueSource
from utils.datetime_serialization import format_instant_rfc3339_utc

DATA_SOURCES: List[Dict[str, str]] = [
    {"key": "ktc", "display_name": "KeepTradeCut", "url": "https://keeptradecut.com/",
     "kind": "trade_value",
     "license_note": "Dynasty/redraft trade values, operated by Jarkley LLC."},
    {"key": "sleeper", "display_name": "Sleeper", "url": "https://sleeper.com/",
     "kind": "platform",
     "license_note": "League, roster, player, stats, projections and research data via the public Sleeper API."},
    {"key": "fantasycalc", "display_name": "FantasyCalc", "url": "https://fantasycalc.com/",
     "kind": "trade_value",
     "license_note": "Trade values derived from real league trades."},
    {"key": "nflverse", "display_name": "nflverse", "url": "https://github.com/nflverse",
     "kind": "injuries",
     "license_note": "Official NFL injury reports. Data by nflverse, licensed CC-BY-4.0."},
    {"key": "tank01", "display_name": "Tank01", "url": "https://tank01.com/",
     "kind": "news_projection",
     "license_note": "Player news and fantasy projections via the Tank01 NFL API (RapidAPI)."},
]


def data_sources_for_bundle(session: Session | None = None) -> List[Dict[str, Any]]:
    """Attribution list with last_synced_at merged in from value_sources when known."""
    session = session or db.session
    try:
        synced = {
            s.source_key: s.last_synced_at
            for s in session.execute(select(ValueSource)).scalars()
        }
    except Exception:  # noqa: BLE001 - attribution must never break the bundle
        synced = {}
    out: List[Dict[str, Any]] = []
    for src in DATA_SOURCES:
        entry: Dict[str, Any] = dict(src)
        ts = synced.get(src["key"])
        entry["last_synced_at"] = format_instant_rfc3339_utc(ts) if ts else None
        out.append(entry)
    return out
