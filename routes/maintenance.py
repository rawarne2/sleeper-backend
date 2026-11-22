"""
Maintenance and batch operations (nightly sync, prewarm).
"""
import time
from datetime import datetime, UTC
from typing import Any, Dict, List, Literal, Optional, get_args

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from starlette.requests import Request

from models.entities import SleeperLeague
from models.extensions import db
from routes.ktc.rankings_cache import invalidate_rankings_cache
from services.daily_refresh import run_daily_refresh
from utils.constants import EXAMPLE_LEAGUE_IDS
from utils.helpers import setup_logging
from web.auth import CRON_AUTH_HINT, cron_authorized
from web.errors import ApiError

router = APIRouter(prefix="/api/maintenance", tags=["Maintenance"])
logger = setup_logging(__name__)


def _prewarm_dashboard_caches() -> Dict[str, Any]:
    """Hit the dashboard endpoint for every persisted league so Redis is warm."""
    # Build league_id -> season map from DB; fall back to example leagues if DB empty.
    rows = db.session.execute(
        select(SleeperLeague.league_id, SleeperLeague.season)
    ).all()
    leagues: list[tuple[str, str]] = [
        (r[0], str(r[1])) for r in rows if r[0] and r[1]
    ] or list(EXAMPLE_LEAGUE_IDS)

    # Import lazily to avoid circular imports; drive the dashboard route
    # in-process via the ASGI test client so the cache warms without a network hop.
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


NightlyStep = Literal[
    "ktc", "leagues", "research", "weekly_stats", "nfl_stats",
    "injuries", "news", "valuations", "prewarm",
]
ALL_STEPS: tuple[str, ...] = get_args(NightlyStep)
_DAILY_STEPS = ("ktc", "leagues", "research", "weekly_stats", "nfl_stats", "injuries", "news")

# Fallback (teams, ppr) pairs when no league is persisted yet. FantasyCalc varies by
# teams/QBs/PPR; KTC + sleeper_proj are config-agnostic.
_DEFAULT_FC_TEAMS_PPR = [(12, 0.5), (12, 1.0), (10, 1.0)]
_FORMAT_ROSTER_POSITIONS = {"superflex": ["SUPER_FLEX"], "1qb": ["QB"]}


def _fc_teams_ppr() -> List[tuple[int, float]]:
    """Distinct (teams, ppr) across persisted leagues, derived like the dashboard's
    ``_fc_config_key`` (roster count, ``rec`` defaulting to 0.5)."""
    import json
    from sqlalchemy import func
    from models.entities import SleeperRoster

    counts = dict(db.session.execute(
        select(SleeperRoster.league_id, func.count()).group_by(SleeperRoster.league_id)
    ).all())
    pairs = set()
    for league_id, raw in db.session.execute(
        select(SleeperLeague.league_id, SleeperLeague.scoring_settings)
    ).all():
        scoring = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
        pairs.add((counts.get(league_id) or 12, float(scoring.get("rec", 0.5) or 0.5)))
    return sorted(pairs) or list(_DEFAULT_FC_TEAMS_PPR)


def _ingest_valuations() -> Dict[str, Any]:
    """Snapshot every valuation source for both formats; per-source fail-soft.

    Ingest is write-on-change, so a second run on the same day (e.g. the vercel.json
    backup cron after GitHub Actions) writes nothing for unchanged values. Retention
    pruning runs afterwards so ``value_snapshots`` growth stays bounded.
    """
    from scrapers.pipelines import ingest_valuations
    from services.valuations.base import SourceUnavailable
    from services.valuations.retention import prune_value_snapshots
    from services.valuations.sources.sleeper_proj import resolve_current_week

    current_season = str(datetime.now(UTC).year)
    try:
        week_settings = {"current_week": resolve_current_week({})}
    except SourceUnavailable:
        week_settings = {}
    teams_ppr = _fc_teams_ppr()
    results: Dict[str, Any] = {}
    for fmt in ("superflex", "1qb"):
        fmt_results: Dict[str, Any] = {"fantasycalc": []}
        for teams, ppr in teams_ppr:
            ls = {"total_rosters": teams, "roster_positions": _FORMAT_ROSTER_POSITIONS[fmt],
                  "scoring_settings": {"rec": ppr}}
            fmt_results["fantasycalc"].append(ingest_valuations(
                ["fantasycalc"], season=current_season, league_format=fmt, league_settings=ls,
            )["fantasycalc"])
        fmt_results.update(ingest_valuations(
            ["ktc", "sleeper_proj", "tank01"], season=current_season,
            league_format=fmt, league_settings=week_settings,
        ))
        results[fmt] = fmt_results
    try:
        results["retention"] = prune_value_snapshots(dry_run=False).deleted
    except Exception as exc:  # noqa: BLE001 - retention must not fail the ingest
        logger.warning("value_snapshots retention skipped: %s", exc)
        db.session.rollback()
        results["retention"] = f"error: {exc}"
    return results


class NightlySyncBody(BaseModel):
    steps: Optional[List[NightlyStep]] = None
    league_ids: Optional[List[str]] = None
    seasons: Optional[List[str]] = None
    research_week: Optional[int] = None
    skip_ktc: bool = False
    skip_leagues: bool = False
    skip_research: bool = False
    backfill_stats: bool = False
    skip_prewarm: bool = False


@router.get("/nightly-sync", operation_id="nightly_sync_get", summary="Run nightly sync pipeline")
@router.post("/nightly-sync", operation_id="nightly_sync_post", summary="Run nightly sync pipeline")
def nightly_sync(request: Request, body: Optional[NightlySyncBody] = Body(None)):
    """
    Full ingest pipeline for scheduled jobs (Vercel Cron uses GET + CRON_SECRET).

    Schedule: GitHub Actions (``.github/workflows/nightly-sync.yml``) drives it as one
    request per step so each stays under Vercel's function limit; the vercel.json
    cron (30 15 * * * UTC) runs every step in one GET as a backup.

    Steps, in order: ktc -> leagues -> research -> weekly_stats -> nfl_stats ->
    injuries -> news -> valuations -> prewarm. Scraping is scoped to the current
    season by default (prior seasons are immutable); pass explicit
    league_ids/seasons to back-fill older data. NFL player ingest is NOT included;
    use POST /api/sleeper/refresh separately (rare).

    Optional JSON body (POST only):
      { "steps": ["ktc"], "league_ids": ["..."], "seasons": ["2025"], "research_week": 1,
        "skip_ktc": false, "skip_leagues": false, "skip_research": false, "skip_prewarm": false }
    Set ``backfill_stats`` to scan weeks 1–18 for the selected seasons.
    Omitting ``steps`` runs every step; the legacy ``skip_*`` flags still apply.
    """
    if not cron_authorized(request):
        raise ApiError(
            "Unauthorized",
            401,
            hint=CRON_AUTH_HINT,
        )

    # For GET (cron) there is no body; treat as all defaults.
    payload = body or NightlySyncBody()
    legacy_skips = {
        "ktc": payload.skip_ktc, "leagues": payload.skip_leagues,
        "research": payload.skip_research, "prewarm": payload.skip_prewarm,
    }
    requested = set(payload.steps or ALL_STEPS)
    steps = [s for s in ALL_STEPS if s in requested and not legacy_skips.get(s)]

    logger.info(
        "Nightly sync started steps=%s (remote=%s)",
        ",".join(steps),
        request.client.host if request.client else None,
    )

    summary: Dict[str, Any] = {"errors": []}
    if any(s in steps for s in _DAILY_STEPS):
        summary = run_daily_refresh(
            league_ids=payload.league_ids,
            seasons=payload.seasons,
            backfill_stats=payload.backfill_stats,
            research_week=payload.research_week,
            skip_ktc="ktc" not in steps,
            skip_leagues="leagues" not in steps,
            skip_research="research" not in steps,
            skip_weekly_stats="weekly_stats" not in steps,
            skip_nfl_stats="nfl_stats" not in steps,
            skip_injuries="injuries" not in steps,
            skip_news="news" not in steps,
        )
    summary["steps"] = steps

    if "ktc" in steps:
        invalidate_rankings_cache()

    if "valuations" in steps:
        try:
            summary["valuations"] = _ingest_valuations()
        except Exception as exc:  # noqa: BLE001 - never fail the cron on valuation ingest
            logger.warning("valuation ingest skipped: %s", exc)
            summary.setdefault("errors", []).append({"step": "valuations", "error": str(exc)})

    if "prewarm" in steps:
        try:
            summary["prewarm"] = _prewarm_dashboard_caches()
        except Exception as e:
            logger.exception("nightly-sync prewarm failed")
            summary.setdefault("errors", []).append(
                {"step": "prewarm", "error": str(e)})

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
