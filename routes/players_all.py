"""GET /api/players/all — full player universe in the unified dashboard shape."""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from flask import Blueprint, jsonify, request

from models.entities import Player
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
    bundle uses.  Players with no KTC row for the format are excluded.
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

    if season_param and (len(season_param) != 4 or not season_param.isdigit()):
        return json_api_error(
            "Query parameter season must be a four-digit year when provided.", 400
        )

    values_by_player_id = latest_player_values(league_format)

    players: List[Player] = db.session.query(Player).all()

    out: List[Dict[str, Any]] = []
    for player in players:
        d = _player_to_dashboard_dict(
            player, league_format, tep_level or "", is_redraft,
            values_by_player_id=values_by_player_id,
        )
        if d is not None:
            out.append(d)

    return jsonify({
        "status": "success",
        "timestamp": utc_now_rfc3339(),
        "league_format": league_format,
        "is_redraft": is_redraft,
        "tep_level": tep_level or "",
        "count": len(out),
        "players": out,
    })
