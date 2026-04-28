from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional, Set, Tuple

from flask import Blueprint, current_app, jsonify, request, Response
from sqlalchemy import func

from cache.redis_dashboard import (
    dashboard_league_cache_key,
    redis_get_dashboard_league_bytes,
    redis_set_dashboard_league_bytes,
)
from managers.database_manager import DatabaseManager
from models.entities import Player, SleeperWeeklyData
from models.extensions import db
from routes.helpers import with_error_handling
from scrapers.sleeper_scraper import SleeperScraper
from utils.constants import (
    PLAYER_NAME_KEY,
    SLEEPER_STATS_AGGREGATE_WEEK_MAX,
    SLEEPER_STATS_AGGREGATE_WEEK_MIN,
)
from utils.datetime_serialization import format_instant_rfc3339_utc
from utils.helpers import validate_parameters

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")
logger = logging.getLogger(__name__)


def _ktc_values_block_for_dashboard(values, tep_level: str) -> Dict[str, Any]:
    """Build the inner KTCValues dict, applying TEP override at the top level."""
    block: Dict[str, Any] = {
        "value": values.value,
        "rank": values.rank,
        "positionalRank": values.positional_rank,
        "overallTier": values.overall_tier,
        "positionalTier": values.positional_tier,
        "tep": {
            "value": values.tep_value,
            "rank": values.tep_rank,
            "positionalRank": values.tep_positional_rank,
            "overallTier": values.tep_overall_tier,
            "positionalTier": values.tep_positional_tier,
        },
        "tepp": {
            "value": values.tepp_value,
            "rank": values.tepp_rank,
            "positionalRank": values.tepp_positional_rank,
            "overallTier": values.tepp_overall_tier,
            "positionalTier": values.tepp_positional_tier,
        },
        "teppp": {
            "value": values.teppp_value,
            "rank": values.teppp_rank,
            "positionalRank": values.teppp_positional_rank,
            "overallTier": values.teppp_overall_tier,
            "positionalTier": values.teppp_positional_tier,
        },
    }
    if tep_level in ("tep", "tepp", "teppp"):
        nested = block[tep_level]
        if nested.get("value") is not None:
            for k in ("value", "rank", "positionalRank", "overallTier", "positionalTier"):
                block[k] = nested[k]
    return block


def _player_to_dashboard_dict(
    player: Player, league_format: str, tep_level: str
) -> Optional[Dict[str, Any]]:
    """
    Slim per-player payload for the dashboard.

    Avoids ``Player.to_dict()`` and only reads the KTC values relationship for
    the requested format, so we never trigger a lazy lookup on the unused side
    or pay for JSON parses the dashboard does not render.
    """
    if league_format == "superflex":
        ktc_values = player.superflex_values
    else:
        ktc_values = player.oneqb_values
    if ktc_values is None:
        return None

    values_block = _ktc_values_block_for_dashboard(ktc_values, tep_level or "")
    return {
        "id": player.id,
        PLAYER_NAME_KEY: player.player_name,
        "position": player.position,
        "team": player.team,
        "sleeper_player_id": player.sleeper_player_id,
        "full_name": player.full_name,
        "last_updated": format_instant_rfc3339_utc(player.last_updated),
        "injury_status": player.injury_status,
        "status": player.status,
        "birth_date": (
            player.birth_date.isoformat() if player.birth_date else None
        ),
        "height": player.height,
        "weight": player.weight,
        "college": player.college,
        "years_exp": player.years_exp,
        "number": player.number,
        "ktc": {
            "age": player.age,
            "oneQBValues": values_block if league_format == "1qb" else None,
            "superflexValues": values_block if league_format == "superflex" else None,
        },
    }


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
    *,
    timings: Optional[Dict[str, float]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    t_q = time.perf_counter()
    # Ownership lives in research_data; points-only weekly rows must not drive this lookup.
    max_week = (
        db.session.query(func.max(SleeperWeeklyData.week))
        .filter(
            SleeperWeeklyData.season == season,
            SleeperWeeklyData.league_type == research_lt,
            SleeperWeeklyData.research_data.isnot(None),
        )
        .scalar()
    )
    if timings is not None:
        timings["ms_research_max_week"] = (time.perf_counter() - t_q) * 1000

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

    t_rows = time.perf_counter()
    rows = (
        SleeperWeeklyData.query.filter(
            SleeperWeeklyData.season == season,
            SleeperWeeklyData.week == int(max_week),
            SleeperWeeklyData.league_type == research_lt,
            SleeperWeeklyData.research_data.isnot(None),
            SleeperWeeklyData.player_id.in_(id_list),
        ).all()
    )
    if timings is not None:
        timings["ms_research_rows"] = (time.perf_counter() - t_rows) * 1000

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


def _load_player_stats(
    season: str,
    research_lt: str,
    roster_player_ids: Set[str],
    *,
    timings: Optional[Dict[str, float]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Load aggregated season stats (avg, total, games) for roster player ids.

    Uses ``SLEEPER_STATS_AGGREGATE_WEEK_*`` (weeks 1–17): week 18 is omitted so the
    last regular-season week does not skew stats (rests, tanking, etc.).
    """
    if not roster_player_ids:
        return {}

    id_list = [x for x in roster_player_ids if x]
    if not id_list:
        return {}

    t_rows = time.perf_counter()
    rows = (
        db.session.query(
            SleeperWeeklyData.player_id,
            func.sum(SleeperWeeklyData.points).label("total_points"),
            func.count(SleeperWeeklyData.id).label("games_played"),
        )
        .filter(
            SleeperWeeklyData.season == season,
            SleeperWeeklyData.league_type == research_lt,
            SleeperWeeklyData.week.between(
                SLEEPER_STATS_AGGREGATE_WEEK_MIN,
                SLEEPER_STATS_AGGREGATE_WEEK_MAX,
            ),
            SleeperWeeklyData.player_id.in_(id_list),
        )
        .group_by(SleeperWeeklyData.player_id)
        .all()
    )
    if timings is not None:
        timings["ms_player_stats"] = (time.perf_counter() - t_rows) * 1000

    stats: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        total = float(row.total_points or 0)
        games = int(row.games_played or 0)
        avg = round(total / games, 2) if games > 0 else 0.0
        stats[str(row.player_id)] = {
            "average_points": avg,
            "total_points": round(total, 2),
            "games_played": games,
        }
    return stats


def _ktc_players_for_roster(
    league_format: str,
    tep_level: Optional[str],
    needed_ids: Set[str],
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Load slim dashboard player dicts from the DB for the roster's Sleeper IDs."""
    players, last_updated = DatabaseManager.get_players_for_sleeper_ids(
        league_format, needed_ids
    )
    if not players:
        return [], None

    out: List[Dict[str, Any]] = []
    for p in players:
        slim = _player_to_dashboard_dict(p, league_format, tep_level or "")
        if slim is not None:
            out.append(slim)

    ts = format_instant_rfc3339_utc(last_updated) if last_updated else None
    return out, ts


def _ensure_league_in_db(league_id: str) -> Optional[str]:
    """Fetch league from Sleeper API and persist it. Returns the season string on success."""
    try:
        league_data = SleeperScraper.scrape_league_data(league_id)
        if not league_data.get("success"):
            return None
        save_result = DatabaseManager.save_league_data(league_data)
        if save_result.get("status") != "success":
            return None
        season = league_data.get("league_info", {}).get("season")
        return str(season) if season else None
    except Exception:
        logger.exception("auto-fetch league failed for %s", league_id)
        return None


def _attach_stats(
    players_slim: List[Dict[str, Any]],
    stats_by_pid: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge per-player season stats into the already-slim payload."""
    for p in players_slim:
        pid = p.get("sleeper_player_id")
        if pid and pid in stats_by_pid:
            p["stats"] = stats_by_pid[pid]
    return players_slim


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

    if season_param and (len(season_param) != 4 or not season_param.isdigit()):
        return jsonify(
            {
                "status": "error",
                "error": "Query parameter season must be a four-digit year when provided.",
            }
        ), 400

    ms_season_lookup = 0.0
    if season_param:
        season = season_param
    else:
        t_se = time.perf_counter()
        exists, raw_season = DatabaseManager.get_league_season_only(league_id)
        ms_season_lookup = (time.perf_counter() - t_se) * 1000
        if not exists:
            # Auto-import league on first request so users can add new league IDs.
            ensured_season = _ensure_league_in_db(league_id)
            if not ensured_season:
                return jsonify(
                    {
                        "status": "error",
                        "error": "Invalid Sleeper league ID or unable to fetch league data.",
                        "league_id": league_id,
                    }
                ), 404
            raw_season = ensured_season
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
    t_rg = time.perf_counter()
    cached = redis_get_dashboard_league_bytes(cache_key)
    ms_redis_get = (time.perf_counter() - t_rg) * 1000

    if cached:
        total_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "dashboard_league cache_hit league_id=%s ms_season_lookup=%.1f "
            "ms_redis_get=%.1f ms_total=%.1f payload_bytes=%s",
            league_id,
            ms_season_lookup,
            ms_redis_get,
            total_ms,
            len(cached),
        )
        resp = Response(cached, mimetype="application/json")
        resp.headers["X-Dashboard-League-Cache"] = "HIT"
        resp.headers["X-Dashboard-League-Payload-Bytes"] = str(len(cached))
        resp.headers["Cache-Control"] = "public, s-maxage=3600, stale-while-revalidate=86400"
        return resp

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

    needed_ids = _roster_player_ids(db_league)
    research_lt = _research_league_type_label(is_redraft)
    own_timings: Dict[str, float] = {}
    flask_app = current_app._get_current_object()

    def _run_players():
        with flask_app.app_context():
            t = time.perf_counter()
            result = _ktc_players_for_roster(
                league_format, tep_level, needed_ids
            )
            own_timings["ms_run_players"] = (time.perf_counter() - t) * 1000
            return result

    def _run_ownership():
        with flask_app.app_context():
            return _load_ownership_and_meta(
                season, research_lt, needed_ids, timings=own_timings
            )

    def _run_stats():
        with flask_app.app_context():
            return _load_player_stats(
                season, research_lt, needed_ids, timings=own_timings
            )

    t_parallel = time.perf_counter()
    with ThreadPoolExecutor(max_workers=3) as pool:
        f_players = pool.submit(_run_players)
        f_ownership = pool.submit(_run_ownership)
        f_stats = pool.submit(_run_stats)
        players, ktc_last_updated = f_players.result()
        ownership, research_meta = f_ownership.result()
        player_stats = f_stats.result()
    ms_parallel = (time.perf_counter() - t_parallel) * 1000

    players = _attach_stats(players, player_stats)

    body: Dict[str, Any] = {
        "league": db_league.get("league"),
        "rosters": db_league.get("rosters") or [],
        "users": db_league.get("users") or [],
        "players": players,
        "ownership": ownership,
        "researchMeta": research_meta,
        "ktcLastUpdated": ktc_last_updated,
    }

    t_json = time.perf_counter()
    payload = json.dumps(
        {"status": "success", "data": body}, separators=(",", ":")
    ).encode("utf-8")
    ms_json = (time.perf_counter() - t_json) * 1000

    t_rs = time.perf_counter()
    redis_set_dashboard_league_bytes(cache_key, payload)
    ms_redis_set = (time.perf_counter() - t_rs) * 1000

    total_ms = (time.perf_counter() - t0) * 1000
    logger.info(
        "dashboard_league cache_miss league_id=%s roster_ids=%s ms_season_lookup=%.1f "
        "ms_league=%.1f ms_parallel=%.1f ms_run_players=%.1f ms_research_max_week=%.1f "
        "ms_research_rows=%.1f ms_player_stats=%.1f ms_json=%.1f ms_redis_get=%.1f "
        "ms_redis_set=%.1f ms_total=%.1f payload_bytes=%s",
        league_id,
        len(needed_ids),
        ms_season_lookup,
        ms_league,
        ms_parallel,
        own_timings.get("ms_run_players", 0.0),
        own_timings.get("ms_research_max_week", 0.0),
        own_timings.get("ms_research_rows", 0.0),
        own_timings.get("ms_player_stats", 0.0),
        ms_json,
        ms_redis_get,
        ms_redis_set,
        total_ms,
        len(payload),
    )

    resp = Response(payload, mimetype="application/json")
    resp.headers["X-Dashboard-League-Cache"] = "MISS"
    resp.headers["X-Dashboard-League-Payload-Bytes"] = str(len(payload))
    resp.headers["Cache-Control"] = (
        "public, s-maxage=3600, stale-while-revalidate=86400"
    )
    return resp
