"""
Maintenance and batch operations (nightly sync, prewarm).
"""
import time
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.requests import Request

from models.entities import SleeperLeague
from routes.ktc.rankings_cache import invalidate_rankings_cache
from services.daily_refresh import run_daily_refresh
from utils.constants import EXAMPLE_LEAGUE_IDS
from utils.helpers import setup_logging
from web.auth import CRON_AUTH_HINT, cron_authorized
from web.errors import ApiError

router = APIRouter(prefix="/api/maintenance", tags=["Maintenance"])
logger = setup_logging()


def _prewarm_dashboard_caches() -> Dict[str, Any]:
    """Hit the dashboard endpoint for every persisted league so Redis is warm."""
    # Build league_id -> season map from DB; fall back to example leagues if DB empty.
    rows = SleeperLeague.query.with_entities(
        SleeperLeague.league_id, SleeperLeague.season
    ).all()
    leagues: list[tuple[str, str]] = [
        (r[0], str(r[1])) for r in rows if r[0] and r[1]
    ] or list(EXAMPLE_LEAGUE_IDS)

    # Import lazily to avoid circular imports; works whether the dashboard route
    # is still Flask-bridged or has been migrated to native FastAPI.
    from starlette.testclient import TestClient
    from app import app as fastapi_app
    client = TestClient(fastapi_app)

    results: List[Dict[str, Any]] = []
    failed = 0
    for league_id, season in leagues:
        t0 = time.perf_counter()
        resp = client.get(
            f"/api/dashboard/league/{league_id}",
            params={
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
                body = resp.json() or {}
            except Exception:
                body = {}
            detail = body.get("details") or body.get("error") or f"HTTP {resp.status_code}"
            entry["error"] = detail
            logger.error(
                "prewarm failed league_id=%s season=%s status=%s error=%s",
                league_id, season, resp.status_code, detail,
            )
        results.append(entry)
    return {"results": results, "failed": failed, "total": len(results)}


@router.get("/health", summary="Maintenance health check")
def maintenance_health():
    """``GET /api/maintenance/health`` — JSON map of maintenance paths and auth expectations (no pipeline run)."""
    return {
        "status": "ok",
        "nightly_sync": {
            "methods": ["GET", "POST"],
            "path": "/api/maintenance/nightly-sync",
            "auth": "Authorization: Bearer <CRON_SECRET> (CRON_SECRET must be set on server)",
            "note": "Vercel Cron invokes GET with the Bearer header; use POST for manual curl.",
        },
    }


class NightlySyncBody(BaseModel):
    league_ids: Optional[List[str]] = None
    seasons: Optional[List[str]] = None
    research_week: Optional[int] = None
    skip_ktc: bool = False
    skip_leagues: bool = False
    skip_research: bool = False
    skip_prewarm: bool = False


@router.api_route("/nightly-sync", methods=["GET", "POST"], summary="Run nightly sync pipeline")
def nightly_sync(request: Request, body: Optional[NightlySyncBody] = Body(None)):
    """
    Full ingest pipeline for scheduled jobs (Vercel Cron uses GET + CRON_SECRET).

    Schedule: see vercel.json (UTC). Repo default 30 15 * * * ~= 11:30 AM Eastern when DST.

    Pipeline: KTC all formats -> leagues -> research per season.
    Scraping is scoped to the current season by default (prior seasons are
    immutable); pass explicit league_ids/seasons to back-fill older data.
    NFL player ingest is NOT included; use POST /api/sleeper/refresh separately (rare).

    Optional JSON body (POST only):
      { "league_ids": ["..."], "seasons": ["2025"], "research_week": 1,
        "skip_ktc": false, "skip_leagues": false, "skip_research": false, "skip_prewarm": false }
    """
    if not cron_authorized(request):
        raise ApiError(
            "Unauthorized",
            401,
            hint=CRON_AUTH_HINT,
        )

    # For GET (cron) there is no body; treat as all defaults.
    payload = body or NightlySyncBody()

    logger.info(
        "Nightly sync started (remote=%s)",
        request.client.host if request.client else None,
    )

    summary = run_daily_refresh(
        league_ids=payload.league_ids,
        seasons=payload.seasons,
        research_week=payload.research_week,
        skip_ktc=payload.skip_ktc,
        skip_leagues=payload.skip_leagues,
        skip_research=payload.skip_research,
    )

    invalidate_rankings_cache()

    if not payload.skip_prewarm:
        try:
            summary["prewarm"] = _prewarm_dashboard_caches()
        except Exception as e:
            logger.exception("nightly-sync prewarm failed")
            summary.setdefault("errors", []).append(
                {"step": "prewarm", "error": str(e)})

    try:
        from scrapers.pipelines import ingest_valuations
        current_season = str(datetime.now(UTC).year)
        # FantasyCalc varies by league config (teams-qbs-ppr), so ingest one snapshot
        # per distinct example-league config. KTC + sleeper_proj are config-agnostic.
        EXAMPLE_FC_CONFIGS = [
            {"total_rosters": 12, "roster_positions": ["SUPER_FLEX"], "scoring_settings": {"rec": 0.5}},
            {"total_rosters": 12, "roster_positions": ["SUPER_FLEX"], "scoring_settings": {"rec": 1.0}},
            {"total_rosters": 10, "roster_positions": ["SUPER_FLEX"], "scoring_settings": {"rec": 1.0}},
            {"total_rosters": 10, "roster_positions": ["QB"], "scoring_settings": {"rec": 1.0}},
        ]
        for fmt in ("superflex", "1qb"):
            for ls in EXAMPLE_FC_CONFIGS:
                ingest_valuations(["fantasycalc"], season=current_season,
                                  league_format=fmt, league_settings=ls)
        for fmt in ("superflex", "1qb"):
            ingest_valuations(["ktc", "sleeper_proj"], season=current_season,
                              league_format=fmt, league_settings={})
    except Exception as exc:  # noqa: BLE001 - never fail the cron on valuation ingest
        logger.warning("valuation ingest skipped: %s", exc)

    return {"status": "success", "summary": summary}


@router.get("/prewarm", summary="Prewarm dashboard caches")
def prewarm(request: Request):
    """``GET /api/maintenance/prewarm`` — same as nightly-sync prewarm; requires cron auth."""
    if not cron_authorized(request):
        raise ApiError("Unauthorized", 401)

    summary = _prewarm_dashboard_caches()
    if summary["failed"]:
        raise ApiError(
            f"{summary['failed']} of {summary['total']} prewarm requests failed",
            500,
            results=summary["results"],
        )
    return {"status": "success", "results": summary["results"]}
