"""Build the dashboard-shaped league bundle from the DB."""
from __future__ import annotations

from typing import Any, Dict, Set

from managers.database_manager import DatabaseManager
from routes.dashboard_league import _ktc_players_for_roster, _roster_player_ids


class LeagueNotFound(LookupError):
    """Raised when the league can't be loaded — maps to 404."""


def load_league_bundle(league_id: str, league_format: str, tep_level: str) -> Dict[str, Any]:
    db_league = DatabaseManager.get_league_data(league_id)
    if db_league.get("status") != "success":
        raise LeagueNotFound(db_league.get("error") or "League not in DB")

    needed: Set[str] = _roster_player_ids(db_league)
    players, _ts = _ktc_players_for_roster(league_format, tep_level or "", needed)
    return {
        "league": db_league.get("league") or {},
        "rosters": db_league.get("rosters") or [],
        "users": db_league.get("users") or [],
        "players": players,
    }
