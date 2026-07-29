"""Read helper: latest news headlines per player (for the dashboard bundle)."""
from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.extensions import db
from models.entities import PlayerNews
from utils.datetime_serialization import format_instant_rfc3339_utc

_DEFAULT_LIMIT = 3


def latest_player_news(
    session: Session | None = None, *, limit_per_player: int = _DEFAULT_LIMIT
) -> Dict[int, List[Dict[str, Any]]]:
    """Return {player_id: [newest-first news dicts]} capped at limit_per_player."""
    session = session or db.session
    rows = session.execute(
        select(PlayerNews).where(PlayerNews.player_id.isnot(None))
    ).scalars().all()

    by_player: Dict[int, List[PlayerNews]] = {}
    for r in rows:
        by_player.setdefault(r.player_id, []).append(r)

    out: Dict[int, List[Dict[str, Any]]] = {}
    for pid, items in by_player.items():
        items.sort(key=lambda r: (r.published_at or r.fetched_at), reverse=True)
        out[pid] = [
            {
                "source": r.source,
                "headline": r.headline,
                "url": r.url,
                "image_url": r.image_url,
                "published_at": format_instant_rfc3339_utc(r.published_at or r.fetched_at),
            }
            for r in items[:limit_per_player]
        ]
    return out
