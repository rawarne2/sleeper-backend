from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set

from flask import Blueprint, jsonify, request
from sqlalchemy import func

from managers import DatabaseManager
from models import SleeperWeeklyData, db
from routes.helpers import filter_players_by_format, with_error_handling
from routes.ktc.rankings_cache import get_cached_rankings_json
from utils import validate_parameters

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")


def _roster_player_ids(league_payload: Dict[str, Any]) -> Set[str]:
    ids: Set[str] = set()
    for r in league_payload.get("rosters") or []:
        if not isinstance(r, dict):
            continue
        for key in ("players", "starters", "reserve", "taxi"):
            raw = r.get(key)
            if isinstance(raw, list):
                for pid in raw:
                    if pid is not None:
                        ids.add(str(pid))
    return ids


def _ownership_entry(blob: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(blob, dict):
        return None
    owned = blob.get("owned")
    started = blob.get("started")
    if owned is None and started is None:
        return None
    out: Dict[str, Any] = {}
    if owned is not None:
        try:
            out["owned"] = float(owned)
        except (TypeError, ValueError):
            out["owned"] = owned
    if started is not None:
        try:
            out["started"] = float(started)
        except (TypeError, ValueError):
            out["started"] = started
    return out or None


def _research_league_type_label(is_redraft: bool) -> str:
    return "redraft" if is_redraft else "dynasty"


def _research_league_type_int(is_redraft: bool) -> int:
    return 1 if is_redraft else 2


def _load_ownership_and_meta(
    season: str, research_lt: str
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    max_week = (
        db.session.query(func.max(SleeperWeeklyData.week))
        .filter(
            SleeperWeeklyData.season == season,
            SleeperWeeklyData.league_type == research_lt,
        )
        .scalar()
    )

    meta: Dict[str, Any] = {
        "season": season,
        "week": int(max_week) if max_week is not None else None,
        "league_type": _research_league_type_int(research_lt == "redraft"),
        "last_updated": None,
    }

    if max_week is None:
        return {}, meta

    rows = SleeperWeeklyData.query.filter_by(
        season=season, week=int(max_week), league_type=research_lt
    ).all()

    ownership: Dict[str, Any] = {}
    last_ts = None
    for row in rows:
        parsed = None
        if row.research_data:
            try:
                parsed = json.loads(row.research_data)
            except json.JSONDecodeError:
                parsed = None
        entry = _ownership_entry(parsed)
        if entry:
            ownership[str(row.player_id)] = entry
        if row.last_updated and (last_ts is None or row.last_updated > last_ts):
            last_ts = row.last_updated

    if last_ts is not None:
        meta["last_updated"] = last_ts.isoformat()
    return ownership, meta


def _ktc_players_for_slice(
    is_redraft: bool,
    league_format: str,
    tep_level: Optional[str],
    needed_ids: Set[str],
) -> tuple[List[Dict[str, Any]], Optional[str]]:
    cached = get_cached_rankings_json(is_redraft, league_format, tep_level or "")
    if cached is not None:
        try:
            outer = json.loads(cached.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeError):
            outer = None
        if isinstance(outer, dict):
            players = outer.get("players") or []
            if isinstance(players, list):
                ts = outer.get("timestamp")
                filtered = [
                    p
                    for p in players
                    if isinstance(p, dict)
                    and str(p.get("sleeper_player_id") or "") in needed_ids
                ]
                return filtered, ts if isinstance(ts, str) else None

    players, last_updated = DatabaseManager.get_players_from_db(league_format)
    if not players:
        return [], None

    players_data = filter_players_by_format(players, league_format, tep_level or "")
    ts = last_updated.isoformat() if last_updated else None
    filtered = [
        p
        for p in players_data
        if str(p.get("sleeper_player_id") or "") in needed_ids
    ]
    return filtered, ts


@dashboard_bp.route("/league/<string:league_id>", methods=["GET"])
@with_error_handling
def get_dashboard_league(league_id: str):
    season = (request.args.get("season") or "").strip()
    if not season or len(season) != 4 or not season.isdigit():
        return jsonify(
            {
                "status": "error",
                "error": "Query parameter season is required (four-digit year).",
            }
        ), 400

    is_redraft_str = request.args.get("is_redraft", "false")
    league_format_str = request.args.get("league_format", "1qb")
    tep_level_str = request.args.get("tep_level", "")

    valid, league_format, tep_level, err = validate_parameters(
        is_redraft_str, league_format_str, tep_level_str
    )
    if not valid:
        return jsonify({"status": "error", "error": err}), 400

    is_redraft = is_redraft_str.lower() == "true"

    db_league = DatabaseManager.get_league_data(league_id)
    if db_league.get("status") != "success":
        return jsonify(
            {
                "status": "error",
                "error": db_league.get("error", "League not found"),
                "hint": "Run the nightly sync or refresh this league so a snapshot exists in the database.",
                "league_id": league_id,
            }
        ), 404

    needed_ids = _roster_player_ids(db_league)
    players, _ = _ktc_players_for_slice(
        is_redraft, league_format, tep_level, needed_ids
    )

    research_lt = _research_league_type_label(is_redraft)
    ownership, research_meta = _load_ownership_and_meta(season, research_lt)

    body: Dict[str, Any] = {
        "league": db_league.get("league"),
        "rosters": db_league.get("rosters") or [],
        "users": db_league.get("users") or [],
        "players": players,
        "ownership": ownership,
        "researchMeta": research_meta,
    }

    return jsonify({"status": "success", "data": body})
