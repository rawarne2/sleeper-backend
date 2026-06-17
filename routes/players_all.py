"""GET /api/players/all — full player universe in the unified dashboard shape."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from flask import Blueprint, Response, jsonify, request

from cache.redis_players_all import (
    redis_get_players_all_bytes,
    redis_set_players_all_bytes,
)
from models.entities import (
    Player,
    PlayerKTCOneQBValues,
    PlayerKTCSuperflexValues,
    SleeperLeague,
    SleeperRoster,
)
from models.extensions import db
from routes.dashboard_league import (
    _attach_research_latest,
    _attach_stats,
    _load_ownership_and_meta,
    _load_player_stats,
    _player_to_dashboard_dict,
    _research_league_type_label,
)
from routes.helpers import json_api_error, with_error_handling
from services.valuations.latest import latest_player_values
from utils.datetime_serialization import utc_now_rfc3339
from utils.helpers import validate_parameters

players_all_bp = Blueprint("players_all", __name__, url_prefix="/api/players")
logger = logging.getLogger(__name__)

# TE-premium dropdown → bonus_rec_te coefficient (previews other configs' points).
TEP_BONUS = {"": 0.0, "tep": 0.5, "tepp": 1.0, "teppp": 1.5}

# Half-PPR baseline so points still populate when no league context is given.
_BASELINE_SCORING = {
    "rec_yd": 0.1,
    "rush_yd": 0.1,
    "rec_td": 6.0,
    "rush_td": 6.0,
    "pass_yd": 0.04,
    "pass_td": 4.0,
    "rec": 0.5,
}


def _resolve_scoring_settings(league_id: str | None, tep: str) -> Dict[str, Any]:
    """Scoring used to compute universe points for the selected league + TEP override."""
    scoring_settings: Dict[str, Any] = {}
    if league_id:
        lg = SleeperLeague.query.filter_by(league_id=str(league_id)).first()
        if lg is not None:
            raw = getattr(lg, "scoring_settings", None) or {}
            scoring_settings = json.loads(raw) if isinstance(raw, str) else dict(raw)
    # The TEP dropdown overrides the TE premium used for points.
    if tep:
        scoring_settings = {
            **scoring_settings,
            "bonus_rec_te": TEP_BONUS.get(tep, scoring_settings.get("bonus_rec_te", 0.0)),
        }
    if not scoring_settings:
        scoring_settings = {**_BASELINE_SCORING, "bonus_rec_te": TEP_BONUS.get(tep, 0.0)}
    return scoring_settings


def _fc_config_key(league_id: str | None, league_format: str) -> str | None:
    """FantasyCalc ``{teams}-{qbs}-{ppr}`` key for the selected league, matching the
    dashboard bundle so All Players reads PPR/team-count-specific FC values. ``None``
    (config-agnostic latest) when no league is selected or it is not yet persisted."""
    if not league_id:
        return None
    lg = SleeperLeague.query.filter_by(league_id=str(league_id)).first()
    if lg is None:
        return None
    num_teams = SleeperRoster.query.filter_by(league_id=str(league_id)).count() or 12
    num_qbs = 2 if league_format == "superflex" else 1
    raw = getattr(lg, "scoring_settings", None) or {}
    scoring = json.loads(raw) if isinstance(raw, str) else dict(raw)
    rec = float(scoring.get("rec", 0.5) or 0.5)
    return f"{num_teams}-{num_qbs}-{rec}"


@players_all_bp.route("/all", methods=["GET"])
@with_error_handling
def get_all_players():
    """``GET /api/players/all`` — full player universe in the unified dashboard shape.

    Query params:
      ``league_format`` (superflex|1qb, default superflex)
      ``is_redraft`` (true|false, default false)
      ``tep_level`` ('', tep, tepp, teppp, default '')
      ``season`` (optional 4-digit year; enables season points + ownership)
      ``league_id`` (optional; loads that league's scoring for season points)

    Returns every ``Player`` row that has a KTC values row for the requested
    format, serialized with the same ``_player_to_dashboard_dict`` the dashboard
    bundle uses. Players with no KTC row for the format are excluded.

    When ``season`` is supplied, season points are computed for the whole player
    universe via the scoring engine using the selected league's ``scoring_settings``
    (or a half-PPR baseline when no ``league_id`` is given). The ``tep`` dropdown
    overrides ``bonus_rec_te`` to preview other TE-premium configs.

    The full universe only changes on a KTC refresh, so responses are cached in
    Redis (keyed by league/config/season, invalidated on refresh). On a cache miss
    the KTC value rows are bulk-loaded in one query rather than per-player, avoiding
    an N+1 over ~500+ players.
    """
    is_redraft_str = request.args.get("is_redraft", "false")
    league_format_str = request.args.get("league_format", "superflex")
    tep_level_str = request.args.get("tep_level", "")
    season_param = (request.args.get("season") or "").strip()
    league_id = (request.args.get("league_id") or "").strip() or None

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

    cached = redis_get_players_all_bytes(
        is_redraft, league_format, tep, season_param, league_id or ""
    )
    if cached is not None:
        resp = Response(cached, mimetype="application/json")
        resp.headers["X-Players-All-Cache"] = "HIT"
        return resp

    values_by_player_id = latest_player_values(
        league_format, fc_config_key=_fc_config_key(league_id, league_format)
    )

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

    # When a season is supplied, attach season points (engine, league-accurate) +
    # research ownership using the same bulk (non-N+1) loaders the dashboard bundle uses.
    research_meta = None
    if season_param:
        scoring_settings = _resolve_scoring_settings(league_id, tep)
        research_lt = _research_league_type_label(is_redraft)
        all_ids = {d["sleeper_player_id"] for d in out if d.get("sleeper_player_id")}
        stats_by_pid = _load_player_stats(season_param, scoring_settings, all_ids)
        ownership, research_meta = _load_ownership_and_meta(season_param, research_lt, all_ids)
        _attach_stats(out, stats_by_pid)
        _attach_research_latest(out, ownership, research_meta)

    payload = {
        "status": "success",
        "timestamp": utc_now_rfc3339(),
        "league_format": league_format,
        "is_redraft": is_redraft,
        "tep_level": tep,
        "count": len(out),
        "players": out,
    }
    if research_meta is not None:
        payload["researchMeta"] = research_meta
    resp = jsonify(payload)
    redis_set_players_all_bytes(
        is_redraft, league_format, tep, season_param, resp.get_data(),
        league_id=league_id or "",
    )
    resp.headers["X-Players-All-Cache"] = "MISS"
    return resp
