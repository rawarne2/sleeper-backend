"""Build the dashboard-shaped league bundle from the DB."""
from __future__ import annotations

from typing import Any, Dict, Set

from managers.database_manager import DatabaseManager
from routes.dashboard_league import (
    _attach_research_latest,
    _attach_stats,
    _ktc_players_for_roster,
    _load_ownership_and_meta,
    _research_league_type_label,
    _roster_player_ids,
)
from services.trade_analyzer.player_stats import load_stats_with_trajectory


class LeagueNotFound(LookupError):
    """Raised when the league can't be loaded — maps to 404."""


def load_league_bundle(
    league_id: str,
    league_format: str,
    tep_level: str,
    *,
    season: str,
    is_redraft: bool,
) -> Dict[str, Any]:
    db_league = DatabaseManager.get_league_data(league_id)
    if db_league.get("status") != "success":
        raise LeagueNotFound(db_league.get("error") or "League not in DB")

    needed: Set[str] = _roster_player_ids(db_league)
    players, _ts = _ktc_players_for_roster(
        league_format, tep_level or "", needed, is_redraft
    )

    research_lt = _research_league_type_label(is_redraft)
    # Ownership + research_meta share a SELECT max(week) under the hood; load it
    # once and thread through to player_stats and build_context so neither
    # re-queries.
    ownership, research_meta = _load_ownership_and_meta(
        season, research_lt, needed
    )
    max_week = research_meta.get("week") if isinstance(research_meta, dict) else None

    stats_by_pid = load_stats_with_trajectory(
        season, research_lt, needed, max_week=max_week
    )
    players = _attach_stats(players, stats_by_pid)
    players = _attach_research_latest(players, ownership, research_meta)

    rosters = db_league.get("rosters") or []
    return {
        "league": db_league.get("league") or {},
        "rosters": rosters,
        "users": db_league.get("users") or [],
        "players": players,
        "total_rosters": len(rosters),
        # Pass-through so build_context can reuse instead of requerying.
        "ownership": ownership,
        "research_meta": research_meta,
    }
