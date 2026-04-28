"""
Maintenance and batch operations (daily refresh, etc.).
"""
import os
import time
from typing import Any, Dict, List

from flask import Blueprint, current_app, jsonify, request

from routes.helpers import with_error_handling
from services.daily_refresh import run_daily_refresh
from routes.ktc.rankings_cache import invalidate_rankings_cache
from utils.helpers import setup_logging

maintenance_bp = Blueprint("maintenance", __name__,
                           url_prefix="/api/maintenance")
logger = setup_logging()


_PREWARM_LEAGUES = [
    ("1333945997071515648", "2026"),
    ("1210364682523656192", "2025"),
    ("1050831680350568448", "2024"),
]


def _prewarm_dashboard_caches() -> Dict[str, Any]:
    """Hit the dashboard endpoint for the example leagues so Redis is warm.

    Returns a summary dict with per-league status and a flag indicating whether
    every prewarm request succeeded.
    """
    client = current_app.test_client()
    results: List[Dict[str, Any]] = []
    failed = 0
    for league_id, season in _PREWARM_LEAGUES:
        t0 = time.perf_counter()
        resp = client.get(
            f"/api/dashboard/league/{league_id}",
            query_string={
                "season": season,
                "league_format": "superflex",
                "is_redraft": "false",
                "tep_level": "tep",
            },
        )
        ms = (time.perf_counter() - t0) * 1000
        entry: Dict[str, Any] = {
            "league_id": league_id,
            "season": season,
            "ms": round(ms, 1),
            "status": resp.status_code,
            "cache": resp.headers.get("X-Dashboard-League-Cache"),
        }
        if resp.status_code != 200:
            failed += 1
            try:
                body = resp.get_json(force=True) or {}
            except Exception:
                body = {}
            detail = body.get("details") or body.get(
                "error") or f"HTTP {resp.status_code}"
            entry["error"] = detail
            logger.error(
                "prewarm failed league_id=%s season=%s status=%s error=%s",
                league_id,
                season,
                resp.status_code,
                detail,
            )
        results.append(entry)
    return {"results": results, "failed": failed, "total": len(results)}


def _cron_authorized() -> bool:
    """
    Authorize a request from Vercel Cron.

    Vercel Cron sends ``Authorization: Bearer <CRON_SECRET>`` and ``x-vercel-cron: 1``.
    Production (``VERCEL_ENV=production``) requires ``CRON_SECRET`` to be set; the
    header alone is not sufficient (headers are spoofable).

    Non-production: if ``CRON_SECRET`` is unset, allow requests that include
    ``x-vercel-cron`` for local/preview testing only.
    """
    secret = (os.getenv("CRON_SECRET") or "").strip()
    vercel_env = (os.getenv("VERCEL_ENV") or "").strip().lower()
    auth = (request.headers.get("Authorization") or "").strip()
    is_vercel_cron = bool(request.headers.get("x-vercel-cron"))

    if vercel_env == "production" and not secret:
        logger.warning(
            "cron auth failed: CRON_SECRET is required when VERCEL_ENV=production"
        )
        return False

    if secret:
        if len(auth) >= 7 and auth[:7].lower() == "bearer ":
            if auth[7:].strip() == secret:
                return True
        logger.warning(
            "cron auth failed: bearer token missing or mismatch (vercel_cron=%s, has_auth=%s)",
            is_vercel_cron,
            bool(auth),
        )
        return False

    if is_vercel_cron:
        logger.warning(
            "cron auth: CRON_SECRET unset; allowing because x-vercel-cron header is present"
        )
        return True

    logger.warning(
        "cron auth failed: CRON_SECRET unset and request lacks x-vercel-cron header"
    )
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

    Schedule: see vercel.json (UTC). Repo default 30 15 * * * ≈ 11:30 AM Eastern when DST.

    Pipeline: KTC all formats -> leagues -> research per season.
    NFL player ingest is NOT included; use POST /api/sleeper/refresh separately (rare).

    Optional JSON body (POST only):
      { "league_ids": ["..."], "seasons": ["2025"], "research_week": 1,
        "skip_ktc": false, "skip_leagues": false, "skip_research": false, "skip_prewarm": false }
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
        research_week=int(
            research_week) if research_week is not None else None,
        skip_ktc=bool(payload.get("skip_ktc")),
        skip_leagues=bool(payload.get("skip_leagues")),
        skip_research=bool(payload.get("skip_research")),
    )

    invalidate_rankings_cache()

    if not bool(payload.get("skip_prewarm")):
        try:
            summary["prewarm"] = _prewarm_dashboard_caches()
        except Exception as e:
            logger.exception("nightly-sync prewarm failed")
            summary.setdefault("errors", []).append(
                {"step": "prewarm", "error": str(e)})

    return jsonify({"status": "success", "summary": summary})


@maintenance_bp.route("/daily-refresh", methods=["POST"])
@with_error_handling
def daily_refresh():
    """
    Run full KTC scrape, league snapshots, and research refresh.

    Pipeline: KTC all formats -> leagues -> research per season.
    NFL player ingest is NOT included; use POST /api/sleeper/refresh separately (rare).

    League IDs default to every league row in the database (or built-in fallbacks).
    Seasons are derived from the league refresh step; pass explicitly when skip_leagues is true.

    Optional JSON body:
      { "league_ids": ["..."], "seasons": ["2025"], "research_week": 1,
        "skip_ktc": false, "skip_leagues": false, "skip_research": false }

    If DAILY_REFRESH_SECRET is set, send header X-Daily-Refresh-Secret matching it.
    Prefer /nightly-sync on a schedule; do not call this from public dashboard clients.
    """
    if not _authorized():
        return jsonify(
            {"status": "error", "error": "Unauthorized",
                "hint": "X-Daily-Refresh-Secret"}
        ), 401

    payload = request.get_json(silent=True) or {}
    league_ids = payload.get("league_ids")
    seasons = payload.get("seasons")
    research_week = payload.get("research_week")

    logger.info("Daily refresh started (remote=%s)", request.remote_addr)

    summary = run_daily_refresh(
        league_ids=league_ids,
        seasons=seasons,
        research_week=int(
            research_week) if research_week is not None else None,
        skip_ktc=bool(payload.get("skip_ktc")),
        skip_leagues=bool(payload.get("skip_leagues")),
        skip_research=bool(payload.get("skip_research")),
    )

    invalidate_rankings_cache()

    return jsonify({"status": "success", "summary": summary})


@maintenance_bp.route("/prewarm", methods=["GET"])
@with_error_handling
def prewarm():
    """Hit dashboard endpoint for known leagues to keep Redis + CDN caches warm."""
    if not _cron_authorized():
        return jsonify({"status": "error", "error": "Unauthorized"}), 401

    summary = _prewarm_dashboard_caches()
    if summary["failed"]:
        return jsonify({
            "status": "error",
            "error": f"{summary['failed']} of {summary['total']} prewarm requests failed",
            "results": summary["results"],
        }), 500
    return jsonify({"status": "success", "results": summary["results"]})
