from __future__ import annotations

import json
import logging
import time
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional, Set

from flask import Blueprint, jsonify, request, Response
from sqlalchemy import func

from cache.redis_dashboard import (
    dashboard_league_cache_key,
    redis_get_dashboard_league_bytes,
    redis_set_dashboard_league_bytes,
)
from managers.database_manager import DatabaseManager
from models.entities import SleeperWeeklyData
from models.extensions import db
from routes.helpers import filter_players_by_format, with_error_handling
from utils.datetime_serialization import format_instant_rfc3339_utc
from utils.helpers import validate_parameters

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")
logger = logging.getLogger(__name__)


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
    season: str,
    research_lt: str,
    roster_player_ids: Set[str],
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

    id_list = [x for x in roster_player_ids if x]
    if not id_list:
        return {}, meta

    rows = (
        SleeperWeeklyData.query.filter(
            SleeperWeeklyData.season == season,
            SleeperWeeklyData.week == int(max_week),
            SleeperWeeklyData.league_type == research_lt,
            SleeperWeeklyData.player_id.in_(id_list),
        ).all()
    )

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
        meta["last_updated"] = format_instant_rfc3339_utc(last_ts)
    return ownership, meta


def _ktc_players_for_roster(
    league_format: str,
    tep_level: Optional[str],
    needed_ids: Set[str],
) -> tuple[List[Dict[str, Any]], Optional[str]]:
    """Load KTC-shaped dicts from DB for roster Sleeper IDs only (no full rankings JSON)."""
    players, last_updated = DatabaseManager.get_players_for_sleeper_ids(
        league_format, needed_ids
    )
    if not players:
        return [], None

    players_data = filter_players_by_format(players, league_format, tep_level or "")
    ts = format_instant_rfc3339_utc(last_updated)
    return players_data, ts


@dashboard_bp.route("/league/<string:league_id>", methods=["GET"])
@with_error_handling
def get_dashboard_league(league_id: str):
    t0 = time.perf_counter()

    season_param = (request.args.get("season") or "").strip()

    is_redraft_str = request.args.get("is_redraft", "false")
    league_format_str = request.args.get("league_format", "1qb")
    tep_level_str = request.args.get("tep_level", "")

    valid, league_format, tep_level, err = validate_parameters(
        is_redraft_str, league_format_str, tep_level_str
    )
    if not valid:
        return jsonify({"status": "error", "error": err}), 400

    is_redraft = is_redraft_str.lower() == "true"

    t_league = time.perf_counter()
    db_league = DatabaseManager.get_league_data(league_id)
    ms_league = (time.perf_counter() - t_league) * 1000

    if db_league.get("status") != "success":
        return jsonify(
            {
                "status": "error",
                "error": db_league.get("error", "League not found"),
                "hint": "Run the nightly sync or refresh this league so a snapshot exists in the database.",
                "league_id": league_id,
            }
        ), 404

    if season_param and (len(season_param) != 4 or not season_param.isdigit()):
        return jsonify(
            {
                "status": "error",
                "error": "Query parameter season must be a four-digit year when provided.",
            }
        ), 400

    if season_param:
        season = season_param
    else:
        raw_season = (db_league.get("league") or {}).get("season")
        season = str(raw_season).strip() if raw_season is not None else ""
        if len(season) != 4 or not season.isdigit():
            season = str(datetime.now(UTC).year)
            logger.warning(
                "dashboard_league league_id=%s missing/invalid season in DB, using %s",
                league_id,
                season,
            )

    cache_key = dashboard_league_cache_key(
        league_id, season, league_format, tep_level or "", is_redraft
    )
    cached = redis_get_dashboard_league_bytes(cache_key)
    if cached:
        total_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "dashboard_league cache_hit league_id=%s ms_total=%.1f",
            league_id,
            total_ms,
        )
        return Response(cached, mimetype="application/json")

    needed_ids = _roster_player_ids(db_league)

    t_players = time.perf_counter()
    players, ktc_last_updated = _ktc_players_for_roster(
        league_format, tep_level, needed_ids
    )
    ms_players = (time.perf_counter() - t_players) * 1000

    research_lt = _research_league_type_label(is_redraft)
    t_own = time.perf_counter()
    ownership, research_meta = _load_ownership_and_meta(
        season, research_lt, needed_ids
    )
    ms_ownership = (time.perf_counter() - t_own) * 1000

    body: Dict[str, Any] = {
        "league": db_league.get("league"),
        "rosters": db_league.get("rosters") or [],
        "users": db_league.get("users") or [],
        "players": players,
        "ownership": ownership,
        "researchMeta": research_meta,
        "ktcLastUpdated": ktc_last_updated,
    }

    total_ms = (time.perf_counter() - t0) * 1000
    logger.info(
        "dashboard_league league_id=%s roster_ids=%s ms_league=%.1f ms_players=%.1f "
        "ms_ownership=%.1f ms_total=%.1f",
        league_id,
        len(needed_ids),
        ms_league,
        ms_players,
        ms_ownership,
        total_ms,
    )

    payload = json.dumps(
        {"status": "success", "data": body}, separators=(",", ":")
    ).encode("utf-8")
    redis_set_dashboard_league_bytes(cache_key, payload)
    return Response(payload, mimetype="application/json")
