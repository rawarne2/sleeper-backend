"""
Maintenance and batch operations (daily refresh, etc.).
"""
import os
from flask import Blueprint, jsonify, request

from routes.helpers import with_error_handling
from services.daily_refresh import run_daily_refresh
from routes.ktc.rankings_cache import invalidate_rankings_cache
from utils import setup_logging

maintenance_bp = Blueprint("maintenance", __name__, url_prefix="/api/maintenance")
logger = setup_logging()


def _cron_authorized() -> bool:
    secret = (os.getenv("CRON_SECRET") or "").strip()
    if not secret:
        return False
    auth = (request.headers.get("Authorization") or "").strip()
    if len(auth) >= 7 and auth[:7].lower() == "bearer ":
        return auth[7:].strip() == secret
    return False


@maintenance_bp.route("/health", methods=["GET"])
@with_error_handling
def maintenance_health():
    """Smoke test that this blueprint is deployed (use if POST /daily-refresh returns 404)."""
    return jsonify(
        {
            "status": "ok",
            "nightly_sync": {
                "methods": ["GET", "POST"],
                "path": "/api/maintenance/nightly-sync",
                "auth": "Authorization: Bearer <CRON_SECRET> (CRON_SECRET must be set on server)",
                "note": "Vercel Cron invokes GET with the Bearer header; use POST for manual curl.",
            },
            "daily_refresh": {
                "method": "POST",
                "path": "/api/maintenance/daily-refresh",
                "note": "Operator/manual use; not for browser clients. Prefer nightly-sync + cron.",
            },
        }
    )


def _authorized() -> bool:
    secret = (os.getenv("DAILY_REFRESH_SECRET") or "").strip()
    if not secret:
        return True
    header = (request.headers.get("X-Daily-Refresh-Secret") or "").strip()
    return header == secret


@maintenance_bp.route("/nightly-sync", methods=["GET", "POST"])
@with_error_handling
def nightly_sync():
    """
    Full ingest pipeline for scheduled jobs (Vercel Cron uses GET + CRON_SECRET).

    Schedule in vercel.json (UTC): e.g. 0 9 * * * ≈ 4:00 AM Eastern Standard Time;
    same expression is 5:00 AM local during Eastern Daylight Time.

    Optional JSON body (POST only): same shape as /daily-refresh.
    """
    if not _cron_authorized():
        return jsonify(
            {
                "status": "error",
                "error": "Unauthorized",
                "hint": "Set CRON_SECRET in the server environment and send Authorization: Bearer <CRON_SECRET>",
            }
        ), 401

    payload = request.get_json(silent=True) or {}
    league_ids = payload.get("league_ids")
    seasons = payload.get("seasons")
    research_week = payload.get("research_week")

    logger.info("Nightly sync started (remote=%s)", request.remote_addr)

    summary = run_daily_refresh(
        league_ids=league_ids,
        seasons=seasons,
        research_week=int(research_week) if research_week is not None else None,
        skip_sleeper_players=bool(payload.get("skip_sleeper_players")),
        skip_ktc=bool(payload.get("skip_ktc")),
        skip_leagues=bool(payload.get("skip_leagues")),
        skip_research=bool(payload.get("skip_research")),
    )

    invalidate_rankings_cache()

    return jsonify({"status": "success", "summary": summary})


@maintenance_bp.route("/daily-refresh", methods=["POST"])
@with_error_handling
def daily_refresh():
    """
    Run Sleeper player merge, full KTC scrape, league snapshots, and research refresh.

    Optional JSON body:
      { "league_ids": ["..."], "seasons": ["2025"], "research_week": 1,
        "skip_sleeper_players": false, "skip_ktc": false, "skip_leagues": false,
        "skip_research": false }

    If DAILY_REFRESH_SECRET is set, send header X-Daily-Refresh-Secret matching it.

    Prefer /nightly-sync on a schedule; do not call this from public dashboard clients.
    """
    if not _authorized():
        return jsonify(
            {"status": "error", "error": "Unauthorized", "hint": "X-Daily-Refresh-Secret"}
        ), 401

    payload = request.get_json(silent=True) or {}
    league_ids = payload.get("league_ids")
    seasons = payload.get("seasons")
    research_week = payload.get("research_week")

    logger.info("Daily refresh started (remote=%s)", request.remote_addr)

    summary = run_daily_refresh(
        league_ids=league_ids,
        seasons=seasons,
        research_week=int(research_week) if research_week is not None else None,
        skip_sleeper_players=bool(payload.get("skip_sleeper_players")),
        skip_ktc=bool(payload.get("skip_ktc")),
        skip_leagues=bool(payload.get("skip_leagues")),
        skip_research=bool(payload.get("skip_research")),
    )

    invalidate_rankings_cache()

    return jsonify({"status": "success", "summary": summary})
