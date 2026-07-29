"""Ingest per-player news headlines from Tank01 (RapidAPI).

Only player-linked items are stored (one row per player+url); general/team news with
no resolvable player is skipped, since the dashboard surfaces news per player. Inactive
unless RAPIDAPI_KEY is set. Old rows are pruned to keep the table bounded.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, UTC
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.extensions import db
from models.entities import Player, PlayerNews
from scrapers import tank01_client

logger = logging.getLogger(__name__)

_SOURCE = "tank01"
_PRUNE_DAYS = 45


def _sleeper_to_player_id(session: Session) -> dict[str, int]:
    rows = session.execute(select(Player.id, Player.sleeper_player_id)).all()
    return {sid: pid for pid, sid in rows if sid}


def _tank_ids(item: dict[str, Any]) -> list[str]:
    raw = item.get("playerID")
    if isinstance(raw, list):
        return [str(x) for x in raw if x]
    return [str(raw)] if raw else []


def ingest_player_news(*, max_items: int = 50, session: Session | None = None) -> dict[str, Any]:
    if not tank01_client.is_configured():
        return {"skipped": "RAPIDAPI_KEY not set"}
    session = session or db.session
    try:
        items = tank01_client.get_news(max_items=max_items)
        tank_to_sleeper = tank01_client.sleeper_id_by_tank_id()
    except Exception as exc:  # noqa: BLE001 - caller records the error
        logger.warning("Tank01 news fetch failed: %s", exc)
        raise

    sleeper_to_pid = _sleeper_to_player_id(session)
    existing = set(
        session.execute(
            select(PlayerNews.url, PlayerNews.player_id).where(PlayerNews.source == _SOURCE)
        ).all()
    )

    now = datetime.now(UTC)
    saved = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        url = (it.get("link") or "").strip()
        title = (it.get("title") or "").strip()
        if not url or not title:
            continue
        image = (it.get("image") or "").strip() or None
        pids = {
            sleeper_to_pid[sid]
            for tid in _tank_ids(it)
            if (sid := tank_to_sleeper.get(tid)) in sleeper_to_pid
        }
        for pid in pids:
            if (url, pid) in existing:
                continue
            session.add(PlayerNews(
                player_id=pid, source=_SOURCE, headline=title[:500], url=url[:600],
                image_url=(image[:600] if image else None), published_at=now,
                raw={}, fetched_at=now,
            ))
            existing.add((url, pid))
            saved += 1

    pruned = _prune_old(session, now)
    session.commit()
    return {"saved": saved, "pruned": pruned, "source_items": len(items)}


def _prune_old(session: Session, now: datetime) -> int:
    cutoff = now - timedelta(days=_PRUNE_DAYS)
    stale = session.execute(
        select(PlayerNews).where(PlayerNews.source == _SOURCE, PlayerNews.fetched_at < cutoff)
    ).scalars().all()
    for row in stale:
        session.delete(row)
    return len(stale)
