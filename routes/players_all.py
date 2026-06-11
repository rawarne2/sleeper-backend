"""GET /api/players/all — full player universe in the unified dashboard shape."""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from flask import Blueprint, Response, jsonify, request

from cache.redis_players_all import (
    redis_get_players_all_bytes,
    redis_set_players_all_bytes,
)
from models.entities import Player, PlayerKTCOneQBValues, PlayerKTCSuperflexValues
from models.extensions import db
from routes.dashboard_league import _player_to_dashboard_dict
from routes.helpers import json_api_error, with_error_handling
from services.valuations.latest import latest_player_values
from utils.datetime_serialization import utc_now_rfc3339
from utils.helpers import validate_parameters

players_all_bp = Blueprint("players_all", __name__, url_prefix="/api/players")
logger = logging.getLogger(__name__)


@players_all_bp.route("/all", methods=["GET"])
@with_error_handling
def get_all_players():
    """``GET /api/players/all`` — full player universe in the unified dashboard shape.

    Query params:
      ``league_format`` (superflex|1qb, default superflex)
      ``is_redraft`` (true|false, default false)
      ``tep_level`` ('', tep, tepp, teppp, default '')
      ``season`` (optional 4-digit year; reserved for future ownership support)

    Returns every ``Player`` row that has a KTC values row for the requested
    format, serialized with the same ``_player_to_dashboard_dict`` the dashboard
    bundle uses. Players with no KTC row for the format are excluded.

    The full universe only changes on a KTC refresh, so responses are cached in
    Redis (invalidated there). On a cache miss the KTC value rows are bulk-loaded
    in one query rather than per-player, avoiding an N+1 over ~500+ players.
    """
    is_redraft_str = request.args.get("is_redraft", "false")
    league_format_str = request.args.get("league_format", "superflex")
    tep_level_str = request.args.get("tep_level", "")
    season_param = (request.args.get("season") or "").strip()

    valid, league_format, tep_level, err = validate_parameters(
        is_redraft_str, league_format_str, tep_level_str
    )
    if not valid:
        return json_api_error(err, 400)

    is_redraft = is_redraft_str.lower() == "true"
    tep = tep_level or ""

    if season_param and (len(season_param) != 4 or not season_param.isdigit()):
        return json_api_error(
            "Query parameter season must be a four-digit year when provided.", 400
        )

    cached = redis_get_players_all_bytes(is_redraft, league_format, tep, season_param)
    if cached is not None:
        resp = Response(cached, mimetype="application/json")
        resp.headers["X-Players-All-Cache"] = "HIT"
        return resp

    values_by_player_id = latest_player_values(league_format)

    # Bulk-load the format's KTC value rows once (one query, not per player).
    ktc_model = (
        PlayerKTCSuperflexValues if league_format == "superflex" else PlayerKTCOneQBValues
    )
    ktc_rows_by_id: Dict[int, Any] = {}
    for row in (
        db.session.query(ktc_model)
        .filter_by(is_redraft=is_redraft)
        .order_by(ktc_model.id)
        .all()
    ):
        ktc_rows_by_id.setdefault(row.player_id, row)

    players: List[Player] = db.session.query(Player).all()

    out: List[Dict[str, Any]] = []
    for player in players:
        d = _player_to_dashboard_dict(
            player, league_format, tep, is_redraft,
            values_by_player_id=values_by_player_id,
            ktc_rows_by_id=ktc_rows_by_id,
        )
        if d is not None:
            out.append(d)

    resp = jsonify({
        "status": "success",
        "timestamp": utc_now_rfc3339(),
        "league_format": league_format,
        "is_redraft": is_redraft,
        "tep_level": tep,
        "count": len(out),
        "players": out,
    })
    redis_set_players_all_bytes(is_redraft, league_format, tep, season_param, resp.get_data())
    resp.headers["X-Players-All-Cache"] = "MISS"
    return resp
