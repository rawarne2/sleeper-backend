"""Build the dashboard-shaped league bundle from the DB."""
from __future__ import annotations

from typing import Any, Dict, Set

from managers.database_manager import DatabaseManager
from routes.dashboard_league import (
    _attach_stats,
    _ktc_players_for_roster,
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
    players, _ts = _ktc_players_for_roster(league_format, tep_level or "", needed)

    research_lt = _research_league_type_label(is_redraft)
    stats_by_pid = load_stats_with_trajectory(season, research_lt, needed)
    players = _attach_stats(players, stats_by_pid)

    rosters = db_league.get("rosters") or []
    return {
        "league": db_league.get("league") or {},
        "rosters": rosters,
        "users": db_league.get("users") or [],
        "players": players,
        "total_rosters": len(rosters),
    }
