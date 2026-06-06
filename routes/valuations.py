# routes/valuations.py
from flask import Blueprint, request, jsonify
from scrapers.pipelines import ingest_valuations
from services.valuations import registry

valuations_bp = Blueprint("valuations", __name__, url_prefix="/api/valuations")


@valuations_bp.route("/refresh", methods=["POST"])
def refresh_valuations():
    body = request.get_json(silent=True) or {}
    league_format = body.get("league_format", "superflex")
    sources = body.get("sources") or registry.known_sources()
    league_settings = body.get("league_settings") or {}
    season = str(body.get("season") or "2026")
    results = ingest_valuations(sources, season=season, league_format=league_format,
                                league_settings=league_settings)
    return jsonify({"results": results}), 200
