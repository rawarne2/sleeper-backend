from fastapi import APIRouter

from managers.database_manager import DatabaseManager
from scrapers.sleeper_scraper import SleeperScraper
from utils.datetime_serialization import utc_now_rfc3339
from utils.helpers import setup_logging
from web.errors import ApiError

router = APIRouter(prefix="/api/sleeper", tags=["Sleeper Players"])
logger = setup_logging(__name__)


@router.post("/refresh", summary="Refresh Sleeper player data")
def refresh_sleeper_data():
    """
    Refresh Sleeper player data and merge with existing KTC data.

    Returns comprehensive player data including physical attributes, career info,
    fantasy data, injury status, and metadata. Merges with KTC players by name/position.

    **Performance Note**: This operation takes 30-60 seconds as it fetches from external APIs.
    """
    logger.info("Starting comprehensive Sleeper data refresh and merge...")

    if not DatabaseManager.verify_database_connection():
        raise ApiError(
            'Database connection failed',
            500,
            details='Cannot establish database connection for Sleeper refresh',
        )

    sleeper_players = SleeperScraper.scrape_sleeper_data()
    if not sleeper_players:
        raise ApiError(
            'Failed to fetch Sleeper player data',
            500,
            details='No active fantasy players found in Sleeper API response',
        )

    logger.info(
        "Successfully fetched %s Sleeper players",
        len(sleeper_players),
    )

    merge_result = DatabaseManager.save_sleeper_data_to_db(sleeper_players)

    if merge_result['status'] == 'error':
        raise ApiError(
            'Failed to merge Sleeper data with KTC players',
            500,
            details=merge_result['error'],
            sleeper_players_fetched=len(sleeper_players),
        )

    return {
        'message': 'Sleeper data refreshed and merged successfully',
        'timestamp': utc_now_rfc3339(),
        'sleeper_data_results': {
            'total_sleeper_players': merge_result['total_sleeper_players'],
            'existing_records_before': merge_result['existing_sleeper_records'],
            'ktc_players_updated': merge_result['updates_made'],
            'new_records_created': merge_result['new_records_created'],
            'match_failures': merge_result['match_failures'],
            'total_processed': merge_result['total_processed'],
        },
        'database_success': True,
        'merge_effective': merge_result['total_processed'] > 0,
    }
