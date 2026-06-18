from fastapi import APIRouter, Request

from managers.database_manager import DatabaseManager
from routes.ktc.rankings_cache import invalidate_rankings_cache
from routes.ktc.refresh_rate_limit import ktc_refresh_rate_limited
from scrapers.ktc_scraper import KTCScraper
from scrapers.pipelines import scrape_and_save_all_ktc_data
from utils.datetime_serialization import utc_now_rfc3339
from utils.helpers import setup_logging
from web.errors import ApiError

router = APIRouter(prefix="/api/ktc", tags=["Bulk Operations"])
logger = setup_logging()


@router.post("/refresh/all", summary="Comprehensive KTC refresh")
def refresh_ktc_all(request: Request):
    """Scrape and save ALL KTC data (dynasty + redraft, 1QB + Superflex, all TEP levels)."""
    ktc_refresh_rate_limited(request)

    logger.info("Verifying database connection before comprehensive refresh...")
    if not DatabaseManager.verify_database_connection():
        raise ApiError(
            "Database connection failed", 500,
            details="Cannot establish database connection before starting refresh operation")

    logger.info("Starting comprehensive KTC refresh for all formats and TEP levels...")
    results = scrape_and_save_all_ktc_data(KTCScraper, DatabaseManager)
    invalidate_rankings_cache()

    if results["overall_status"] == "error":
        raise ApiError(
            "Comprehensive refresh failed", 500,
            details=results.get("error", "Both dynasty and redraft operations failed"),
            results=results)
    if results["overall_status"] == "partial_success":
        return {
            "message": "Comprehensive refresh partially successful",
            "warning": "One of the operations failed",
            "timestamp": utc_now_rfc3339(),
            "results": results,
        }
    return {
        "message": "Comprehensive refresh completed successfully",
        "timestamp": utc_now_rfc3339(),
        "results": results,
        "summary": {
            "dynasty_players": results["dynasty"]["players_count"],
            "dynasty_saved": results["dynasty"]["db_count"],
            "redraft_players": results["redraft"]["players_count"],
            "redraft_saved": results["redraft"]["db_count"],
            "total_players": (results["dynasty"]["players_count"]
                              + results["redraft"]["players_count"]),
            "total_saved": (results["dynasty"]["db_count"]
                            + results["redraft"]["db_count"]),
        },
    }
