from fastapi import APIRouter
from fastapi.responses import JSONResponse

from cache.redis_dashboard import invalidate_dashboard_league
from managers.database_manager import DatabaseManager
from scrapers.sleeper_scraper import SleeperScraper
from utils.datetime_serialization import utc_now_rfc3339
from utils.helpers import setup_logging
from web.errors import ApiError

router = APIRouter(prefix="/api/sleeper/league", tags=["Sleeper Leagues"])
logger = setup_logging(__name__)


@router.get("/{league_id}", summary="Get comprehensive league data")
def get_league_data(league_id: str):
    """
    Get comprehensive league data (league info, rosters, users). Returns complete league
    configuration, all rosters with player IDs, and user information. Checks database
    first, falls back to Sleeper API.
    """
    # Try to get from database first
    db_result = DatabaseManager.get_league_data(league_id)

    if db_result.get('status') == 'success':
        return {
            'status': 'success',
            'data': db_result,
            'source': 'database',
            'timestamp': utc_now_rfc3339(),
        }

    # If not in database, fetch from Sleeper API
    logger.info(
        "League not found in database, fetching from Sleeper API: %s", league_id)
    league_data = SleeperScraper.scrape_league_data(league_id)

    if not league_data.get('success'):
        raise ApiError(
            'Invalid league ID or failed to fetch league data',
            404,
            details=league_data.get('error'),
            league_id=league_id,
        )

    # Save to database
    save_result = DatabaseManager.save_league_data(league_data)

    if save_result.get('status') != 'success':
        logger.warning("Failed to save league data to database: %s",
                       save_result.get('error'))

    return {
        'status': 'success',
        'data': league_data,
        'source': 'sleeper_api',
        'database_saved': save_result.get('status') == 'success',
        'timestamp': utc_now_rfc3339(),
    }


@router.get("/{league_id}/rosters", summary="Get league rosters")
def get_league_rosters(league_id: str):
    """Get league rosters data for all teams in the league."""
    # First try to get full league data (uses caching)
    league_result = DatabaseManager.get_league_data(league_id)

    if league_result.get('status') == 'success':
        return {
            'status': 'success',
            'league_id': league_id,
            'rosters': league_result['rosters'],
            'count': len(league_result['rosters']),
            'last_updated': league_result.get('last_updated'),
            'timestamp': utc_now_rfc3339(),
        }

    # Fallback to direct API call if not in database
    rosters_data = SleeperScraper.fetch_league_rosters(league_id)

    if rosters_data is None:
        raise ApiError(
            'Invalid league ID or failed to fetch roster data',
            404,
            league_id=league_id,
        )

    return {
        'status': 'success',
        'league_id': league_id,
        'rosters': rosters_data,
        'count': len(rosters_data),
        'source': 'direct_api',
        'timestamp': utc_now_rfc3339(),
    }


@router.get("/{league_id}/users", summary="Get league users")
def get_league_users(league_id: str):
    """Get league users data for all participants in the league."""
    # First try to get full league data (uses caching)
    league_result = DatabaseManager.get_league_data(league_id)

    if league_result.get('status') == 'success':
        return {
            'status': 'success',
            'league_id': league_id,
            'users': league_result['users'],
            'count': len(league_result['users']),
            'last_updated': league_result.get('last_updated'),
            'timestamp': utc_now_rfc3339(),
        }

    # Fallback to direct API call if not in database
    users_data = SleeperScraper.fetch_league_users(league_id)

    if users_data is None:
        raise ApiError(
            'Invalid league ID or failed to fetch users data',
            404,
            league_id=league_id,
        )

    return {
        'status': 'success',
        'league_id': league_id,
        'users': users_data,
        'count': len(users_data),
        'source': 'direct_api',
        'timestamp': utc_now_rfc3339(),
    }


@router.post("/{league_id}", operation_id="refresh_league_data_post", summary="Refresh/Update league data")
@router.put("/{league_id}", operation_id="refresh_league_data_put", summary="Refresh/Update league data")
def refresh_league_data(league_id: str):
    """
    Refresh all league data from Sleeper API (league info, rosters, users).

    Returns the full results dict even on 404/500 — the HTTP status code signals
    the outcome but the body is always the results object (not the error envelope).
    """
    logger.info("League data refresh requested for league_id: %s", league_id)

    results = {
        'status': 'success',
        'timestamp': utc_now_rfc3339(),
        'league_id': league_id,
        'league_data': None,
        'users_data': None,
        'rosters_data': None,
        'errors': []
    }

    try:
        # Refresh main league data
        logger.info("Refreshing league data for league_id: %s", league_id)
        league_data = SleeperScraper.scrape_league_data(league_id)

        if league_data.get('success'):
            save_result = DatabaseManager.save_league_data(league_data)
            if save_result.get('status') == 'success':
                invalidate_dashboard_league(league_id)
                results['league_data'] = {
                    'status': 'success',
                    'save_result': save_result
                }
                results['users_data'] = {
                    'status': 'success',
                    'users_saved': save_result.get('users_saved'),
                    'users_updated': save_result.get('users_updated'),
                }
                results['rosters_data'] = {
                    'status': 'success',
                    'rosters_saved': save_result.get('rosters_saved'),
                    'rosters_updated': save_result.get('rosters_updated'),
                }
                logger.info(
                    "Successfully refreshed league data for league_id: %s", league_id)
            else:
                results['league_data'] = {
                    'status': 'error',
                    'save_result': save_result
                }
                results['errors'].append({
                    'type': 'league_save',
                    'error': save_result.get('error', 'save failed'),
                })
                results['users_data'] = {
                    'status': 'error',
                    'message': save_result.get('error', 'save failed'),
                }
                results['rosters_data'] = {
                    'status': 'error',
                    'message': save_result.get('error', 'save failed'),
                }
        else:
            results['errors'].append({
                'type': 'league_data',
                'error': league_data.get('error')
            })
            results['league_data'] = {'status': 'error'}
            results['users_data'] = {'status': 'skipped'}
            results['rosters_data'] = {'status': 'skipped'}

        logger.info(
            "League data refresh completed for league_id: %s", league_id)

    except Exception as e:
        logger.error("Error refreshing data for league %s: %s", league_id, e)
        results['errors'].append({
            'type': 'general_error',
            'error': str(e)
        })

    # Set overall status based on errors
    if results['errors']:
        success_count = sum(1 for key in ['league_data', 'users_data', 'rosters_data']
                            if results[key] and results[key].get('status') == 'success')
        if success_count == 0:
            results['status'] = 'error'
        else:
            results['status'] = 'partial_success'

    # Include the league data we just refreshed
    if results['league_data'] and results.get('league_data').get('status') == 'success':
        results['data'] = results.get('league_data').get('save_result')
        results['source'] = 'database'
    else:
        results['data'] = None
        results['source'] = 'sleeper_api'

    http_code = 200
    if results['status'] == 'error':
        scrape_failed = any(
            e.get('type') == 'league_data' for e in results['errors'])
        http_code = 404 if scrape_failed else 500

    # Return the full results dict even on 404/500 (NOT the ApiError envelope)
    return JSONResponse(results, status_code=http_code)
