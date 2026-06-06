from __future__ import annotations
from typing import Any, Dict
from sqlalchemy import func
from models.entities import ValueSnapshot
from models.extensions import db
from services.valuations.blend import blend_values, default_weights

_BLEND_SOURCES = ("ktc", "fantasycalc")


def _latest_rows(league_format: str):
    sub = (
        db.session.query(
            ValueSnapshot.player_id.label("aid"), ValueSnapshot.source_key,
            ValueSnapshot.metric_key, func.max(ValueSnapshot.as_of).label("mx"),
        )
        .filter(ValueSnapshot.league_format == league_format,
                ValueSnapshot.player_id.isnot(None))
        .group_by(ValueSnapshot.player_id, ValueSnapshot.source_key, ValueSnapshot.metric_key)
        .subquery()
    )
    return (
        db.session.query(ValueSnapshot)
        .join(sub, (ValueSnapshot.player_id == sub.c.aid)
              & (ValueSnapshot.source_key == sub.c.source_key)
              & (ValueSnapshot.metric_key == sub.c.metric_key)
              & (ValueSnapshot.as_of == sub.c.mx))
        .all()
    )


def latest_player_values(league_format: str) -> Dict[int, Dict[str, Any]]:
    rows = _latest_rows(league_format)
    out: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        entry = out.setdefault(r.player_id, {"sources": {}, "projection": {}, "blended": None})
        if r.metric_key == "value":
            src = entry["sources"].setdefault(r.source_key, {})
            src["value"] = r.metric_value
            src["rank"] = r.rank
        elif r.metric_key in ("redraft_value", "trade_frequency", "volatility", "trend_30day"):
            entry["sources"].setdefault(r.source_key, {})[r.metric_key] = r.metric_value
        elif r.metric_key in ("proj_ros", "proj_week"):
            entry["projection"][r.metric_key] = r.metric_value

    per_source = {
        s: {pid: e["sources"][s]["value"]
            for pid, e in out.items() if s in e["sources"] and "value" in e["sources"][s]}
        for s in _BLEND_SOURCES
    }
    for pid, val in blend_values(per_source, default_weights()).items():
        out[pid]["blended"] = val
    return out
