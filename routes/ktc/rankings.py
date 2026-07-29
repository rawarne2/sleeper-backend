from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response

from managers.database_manager import DatabaseManager
from routes.helpers import filter_players_by_format
from routes.ktc.rankings_cache import (
    get_cached_rankings_json,
    invalidate_rankings_cache,
    set_cached_rankings_json,
)
from routes.ktc.refresh_rate_limit import ktc_refresh_rate_limited
from services.ktc_refresh_async import (
    execute_ktc_refresh_pipeline,
    get_refresh_job,
    try_begin_async_job,
)
from utils.datetime_serialization import format_instant_rfc3339_utc, utc_now_rfc3339
from utils.helpers import setup_logging
from web.errors import ApiError
from web.params import validate_ktc_params
from web.schemas import KtcRefreshAccepted, KtcRefreshJobStatus

router = APIRouter(prefix="/api/ktc", tags=["KTC Player Rankings"])
logger = setup_logging(__name__)

_SYNC_TRUE = {"1", "true", "yes"}
_SYNC_FALSE = {"0", "false", "no"}


def _wants_sync(sync: str | None, async_: str | None) -> bool:
    """Blocking pipeline (multi-minute). Use sync=1 for tests or operators."""
    s = (sync or "").strip().lower()
    if s in _SYNC_TRUE:
        return True
    if s in _SYNC_FALSE:
        return False
    a = (async_ or "").strip().lower()
    if a in _SYNC_FALSE:
        return True
    return False


@router.post("/refresh", operation_id="refresh_rankings_post",
             summary="Refresh/Update KTC player rankings",
             responses={
                 202: {"model": KtcRefreshAccepted,
                       "description": "Refresh accepted; poll poll_url"},
                 200: {"description": "Blocking sync=1 pipeline result"},
             })
@router.put("/refresh", operation_id="refresh_rankings_put",
            summary="Refresh/Update KTC player rankings",
            responses={202: {"model": KtcRefreshAccepted}})
def refresh_rankings(request: Request,
                     is_redraft: str = Query("false"),
                     league_format: str = Query("1qb"),
                     tep_level: str = Query(""),
                     sync: str | None = Query(None),
                     async_: str | None = Query(None, alias="async")):
    """Refresh/Update KTC player rankings.

    Default returns 202 and enqueues scrape + DB save in a background thread; pass
    ``sync=1`` (or ``async=0``) to run the full pipeline in the request and get 200.
    """
    ktc_refresh_rate_limited(request)
    p = validate_ktc_params(is_redraft, league_format, tep_level)

    if _wants_sync(sync, async_):
        logger.info("KTC refresh (sync=1): full pipeline in request thread")
        outcome = execute_ktc_refresh_pipeline(p.league_format, p.is_redraft, p.tep_level)
        return JSONResponse(outcome.body, status_code=outcome.status_code)

    logger.info("KTC refresh: enqueue background job (use sync=1 for blocking)")
    if not DatabaseManager.verify_database_connection():
        logger.error("Database connection verification failed before refresh enqueue")
        raise ApiError(
            "Database connection failed", 500,
            details="Cannot establish database connection before starting refresh operation")

    job_id, already_running = try_begin_async_job(p.league_format, p.is_redraft, p.tep_level)
    return JSONResponse({
        "accepted": True,
        "status": "queued",
        "job_id": job_id,
        "already_running": already_running,
        "message": ("KTC refresh accepted; running in background"
                    + (" (already in progress for this configuration)"
                       if already_running else "")),
        "poll_url": f"/api/ktc/refresh/status/{job_id}",
        "is_redraft": p.is_redraft,
        "league_format": p.league_format,
        "tep_level": p.tep_level or "",
        "hint": "Refetch GET /api/dashboard/league/<id> until ktcLastUpdated advances.",
    }, status_code=202)


@router.get("/refresh/status/{job_id}", summary="Poll async KTC refresh job status",
            response_model=KtcRefreshJobStatus)
def refresh_status(job_id: str):
    rec = get_refresh_job(job_id)
    if not rec:
        raise ApiError("Unknown job_id", 404, job_id=job_id)
    return {k: rec[k] for k in ("job_id", "status", "created_at", "finished_at",
                                "league_format", "is_redraft", "tep_level",
                                "error", "summary")}


@router.post("/cleanup", summary="Clean up incomplete data")
def cleanup_database(is_redraft: str = Query("false"),
                     league_format: str = Query("1qb"),
                     tep_level: str = Query("")):
    p = validate_ktc_params(is_redraft, league_format, tep_level)
    result = DatabaseManager.cleanup_incomplete_data(p.league_format, p.is_redraft, p.tep_level)
    if result["status"] == "error":
        raise ApiError("Cleanup operation failed", 500,
                       details=result["error"], configuration=result["configuration"])
    invalidate_rankings_cache()
    return {"message": "Database cleanup completed", "timestamp": utc_now_rfc3339(),
            "cleanup_result": result}


@router.get("/rankings", summary="Get stored player rankings")
def get_rankings(is_redraft: str = Query("false"),
                 league_format: str = Query("1qb"),
                 tep_level: str = Query("")):
    p = validate_ktc_params(is_redraft, league_format, tep_level)
    headers = {"Cache-Control": "public, max-age=3600, stale-while-revalidate=86400"}

    cached = get_cached_rankings_json(p.is_redraft, p.league_format, p.tep_level)
    if cached is not None:
        return Response(cached, media_type="application/json",
                        headers={**headers, "X-Rankings-Cache": "HIT"})

    players, last_updated = DatabaseManager.get_players_from_db(p.league_format, p.is_redraft)
    if not players:
        raise ApiError(
            "No rankings found for the specified parameters", 404,
            suggestion="Try POST /api/ktc/refresh/all or POST /api/ktc/refresh to populate data",
            parameters={"is_redraft": p.is_redraft,
                        "league_format": p.league_format, "tep_level": p.tep_level})

    players_data = filter_players_by_format(players, p.league_format, p.tep_level, p.is_redraft)
    payload = {"timestamp": format_instant_rfc3339_utc(last_updated),
               "is_redraft": p.is_redraft, "league_format": p.league_format,
               "tep_level": p.tep_level, "count": len(players_data), "players": players_data}
    json_bytes = set_cached_rankings_json(p.is_redraft, p.league_format, p.tep_level, payload)
    return Response(json_bytes, media_type="application/json",
                    headers={**headers, "X-Rankings-Cache": "MISS"})
