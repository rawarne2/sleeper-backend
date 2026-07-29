"""Read helper: latest official injury report per player (for the dashboard bundle)."""
from __future__ import annotations

from typing import Any, Dict

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.extensions import db
from models.entities import PlayerInjuryReport


def latest_injury_reports(session: Session | None = None) -> Dict[int, Dict[str, Any]]:
    """Return {player_id: latest injury-report dict}, newest by (season, week)."""
    session = session or db.session
    rows = session.execute(select(PlayerInjuryReport)).scalars().all()
    latest: Dict[int, PlayerInjuryReport] = {}
    for r in rows:
        cur = latest.get(r.player_id)
        if cur is None or (str(r.season), r.week) > (str(cur.season), cur.week):
            latest[r.player_id] = r
    return {
        pid: {
            "source": r.source,
            "season": r.season,
            "week": r.week,
            "report_status": r.report_status,
            "report_primary_injury": r.report_primary_injury,
            "report_secondary_injury": r.report_secondary_injury,
            "practice_status": r.practice_status,
            "practice_primary_injury": r.practice_primary_injury,
        }
        for pid, r in latest.items()
    }
