from datetime import datetime, UTC
from flask import Blueprint, jsonify, request
from functools import wraps

from models import db
from scrapers import SleeperScraper, KTCScraper
from managers import PlayerMerger, FileManager, DatabaseManager
from utils import (validate_refresh_parameters, scrape_and_process_data,
                   save_and_verify_database, perform_file_operations,
                   validate_parameters, BOOLEAN_STRINGS, setup_logging)

# Create a blueprint for routes
api_bp = Blueprint('api', __name__, url_prefix='/api')

logger = setup_logging()


def with_error_handling(f):
    """Decorator for consistent error handling."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logger.error("Unexpected error in %s: %s", f.__name__, e)
            return jsonify({
                'status': 'error',
                'error': 'Internal server error',
                'details': str(e),
                'timestamp': datetime.now(UTC).isoformat()
            }), 500
    return decorated_function


@api_bp.route('/sleeper/refresh', methods=['POST'])
def refresh_sleeper_data():
    """
    Endpoint to refresh Sleeper player data and merge with existing KTC data.

    Implements comprehensive integration:
    - Fetches data from Sleeper API
    - Merges with existing KTC players using name, birth_date, and position matching
    - Saves additional data to database (excluding injury fields)
    - Uses batch processing for efficiency
    - Prevents redundant imports

    Returns:
        JSON response with refresh results including merge statistics
    """
    try:
        logger.info("Starting comprehensive Sleeper data refresh and merge...")

        # Verify database connection
        if not DatabaseManager.verify_database_connection():
            return jsonify({
                'error': 'Database connection failed',
                'details': 'Cannot establish database connection for Sleeper refresh'
            }), 500

        # Fetch and process Sleeper player data using new SleeperScraper
        sleeper_players = SleeperScraper.scrape_sleeper_data()
        if not sleeper_players:
            return jsonify({
                'error': 'Failed to fetch Sleeper player data',
                'details': 'No active fantasy players found in Sleeper API response'
            }), 500

        logger.info("Successfully fetched %s Sleeper players",
                    len(sleeper_players))

        # Merge Sleeper data with existing KTC players in database
        merge_result = DatabaseManager.merge_sleeper_data_with_ktc(
            sleeper_players)

        if merge_result['status'] == 'error':
            return jsonify({
                'error': 'Failed to merge Sleeper data with KTC players',
                'details': merge_result['error'],
                'sleeper_players_fetched': len(sleeper_players)
            }), 500

        # Return comprehensive success response
        return jsonify({
            'message': 'Sleeper data refreshed and merged successfully',
            'timestamp': datetime.now(UTC).isoformat(),
            'sleeper_data_results': {
                'total_sleeper_players': merge_result['total_sleeper_players'],
                'existing_records_before': merge_result['existing_sleeper_records'],
                'ktc_players_updated': merge_result['updates_made'],
                'new_records_created': merge_result['new_records_created'],
                'match_failures': merge_result['match_failures'],
                'total_processed': merge_result['total_processed']
            },
            'database_success': True,
            'merge_effective': merge_result['total_processed'] > 0
        })

    except Exception as e:
        logger.error("Error refreshing Sleeper data: %s", e)
        return jsonify({
            'error': 'Internal server error during Sleeper refresh',
            'details': str(e),
            'database_success': False
        }), 500


@api_bp.route('/ktc/refresh', methods=['POST'])
def refresh_rankings():
    """
    Endpoint to fetch fresh data from KTC and store in database.

    Query Parameters:
        is_redraft (str): 'true' or 'false', default 'false'
        league_format (str): '1qb' or 'superflex', default '1qb'
        tep_level (str): '', 'tep', 'tepp', or 'teppp', default ''

    Returns:
        JSON response with refresh results and operation status
    """
    try:
        # Validate parameters
        valid, league_format, tep_level, is_redraft, error_msg = validate_refresh_parameters(
            request)
        if not valid:
            return jsonify({'error': error_msg}), 400
        # breakpoint()
        # Verify database connection
        logger.info("Verifying database connection before refresh...")
        if not DatabaseManager.verify_database_connection():
            logger.error(
                "Database connection verification failed before refresh")
            return jsonify({
                'error': 'Database connection failed',
                'details': 'Cannot establish database connection before starting refresh operation'
            }), 500

        # Scrape and process data
        players_sorted, scrape_error = scrape_and_process_data(
            KTCScraper, league_format, is_redraft, tep_level)
        if scrape_error:
            return jsonify({
                'error': 'No players found during scraping',
                'details': scrape_error
            }), 500

        # Save to database and verify
        added_count, db_error = save_and_verify_database(
            DatabaseManager, players_sorted, league_format, is_redraft, tep_level)
        if db_error:
            return jsonify({
                'error': 'Database operation failed',
                'details': db_error,
                'scraped_count': len(players_sorted),
                'database_success': False
            }), 500

        # Perform file operations (optional - don't fail if these fail)
        file_saved, s3_uploaded = perform_file_operations(
            FileManager, players_sorted, added_count, league_format, is_redraft, tep_level)

        # Return success response
        return jsonify({
            'message': 'Rankings refreshed successfully',
            'timestamp': datetime.now(UTC).isoformat(),
            'database_success': True,
            'file_saved': file_saved,
            's3_uploaded': s3_uploaded,
            'players_sorted': players_sorted,
            'operations_summary': {
                'players_count': len(players_sorted),
                'database_saved_count': added_count,
                'file_saved': file_saved,
                's3_uploaded': s3_uploaded
            }
        })

    except Exception as e:
        logger.error("Error refreshing rankings: %s", e)
        return jsonify({
            'error': 'Internal server error during refresh',
            'details': str(e),
            'database_success': False,
            'context': 'Error occurred in main refresh flow'
        }), 500


@api_bp.route('/ktc/health', methods=['GET'])
def health_check():
    """
    Database health check endpoint.

    Returns:
        JSON response with health status and timestamp
    """
    try:
        logger.info('Performing health check...')

        # Test database connection
        connection_ok = DatabaseManager.verify_database_connection()
        timestamp = datetime.now(UTC).isoformat()

        if not connection_ok:
            return jsonify({
                'status': 'unhealthy',
                'database': 'connection_failed',
                'timestamp': timestamp
            }), 500

        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'timestamp': timestamp
        })

    except Exception as e:
        logger.error("Health check failed: %s", e)
        return jsonify({
            'status': 'unhealthy',
            'database': 'error',
            'error': str(e),
            'timestamp': datetime.now(UTC).isoformat()
        }), 500


@api_bp.route('/ktc/cleanup', methods=['POST'])
def cleanup_database():
    """
    Endpoint to clean up incomplete or corrupted data.

    Query Parameters:
        is_redraft (str): 'true' or 'false', default 'false'
        league_format (str): '1qb' or 'superflex', default '1qb'  
        tep_level (str): '', 'tep', 'tepp', or 'teppp', default ''

    Returns:
        JSON response with cleanup results
    """
    try:
        # Get and validate parameters
        is_redraft_str = request.args.get('is_redraft', 'false')
        league_format_str = request.args.get('league_format', '1qb')
        tep_level_str = request.args.get('tep_level', '')

        valid, league_format, tep_level, error_msg = validate_parameters(
            is_redraft_str, league_format_str, tep_level_str
        )

        if not valid:
            return jsonify({'error': error_msg}), 400

        is_redraft = is_redraft_str.lower() in BOOLEAN_STRINGS

        # Perform cleanup
        cleanup_result = DatabaseManager.cleanup_incomplete_data(
            league_format, is_redraft, tep_level)

        if cleanup_result['status'] == 'error':
            return jsonify({
                'error': 'Cleanup operation failed',
                'details': cleanup_result['error'],
                'configuration': cleanup_result['configuration']
            }), 500

        return jsonify({
            'message': 'Database cleanup completed',
            'timestamp': datetime.now(UTC).isoformat(),
            'cleanup_result': cleanup_result
        })

    except Exception as e:
        logger.error("Error during cleanup endpoint: %s", e)
        return jsonify({
            'error': 'Internal server error during cleanup',
            'details': str(e)
        }), 500


@api_bp.route('/ktc/rankings', methods=['GET'])
def get_rankings():
    """
    Endpoint to retrieve stored rankings with optional filtering.

    Query Parameters:
        is_redraft (str): 'true' or 'false', default 'false'
        league_format (str): '1qb' or 'superflex', default '1qb'
        tep_level (str): '', 'tep', 'tepp', or 'teppp', default ''

    Returns:
        JSON response with player rankings data
    """
    try:
        # Get and validate parameters
        is_redraft_str = request.args.get('is_redraft', 'false')
        league_format_str = request.args.get('league_format', '1qb')
        tep_level_str = request.args.get('tep_level', '')
        # breakpoint()
        valid, league_format, tep_level, error_msg = validate_parameters(
            is_redraft_str, league_format_str, tep_level_str
        )

        if not valid:
            return jsonify({'error': error_msg}), 400

        is_redraft = is_redraft_str.lower() in BOOLEAN_STRINGS

        # Query the database
        players, last_updated = DatabaseManager.get_players_from_db(
            league_format, is_redraft, tep_level)

        if not players:
            return jsonify({
                'error': 'No rankings found for the specified parameters',
                'suggestion': 'Try calling the /api/ktc/refresh endpoint first to populate data',
                'parameters': {
                    'is_redraft': is_redraft,
                    'league_format': league_format,
                    'tep_level': tep_level
                }
            }), 404

        # Convert players to dict format
        players_data = [player.to_dict() for player in players]

        return jsonify({
            'timestamp': last_updated.isoformat() if last_updated else None,
            'is_redraft': is_redraft,
            'league_format': league_format,
            'tep_level': tep_level,
            'count': len(players),
            'players': players_data
        })

    except Exception as e:
        logger.error("Error retrieving rankings: %s", e)
        return jsonify({
            'error': 'Internal server error during rankings retrieval',
            'details': str(e)
        }), 500


# ============================================================================
# SLEEPER LEAGUE ENDPOINTS
# ============================================================================

@api_bp.route('/sleeper/league/<string:league_id>', methods=['GET'])
@with_error_handling
def get_league_data(league_id: str):
    """
    Get comprehensive league data (league info, rosters, users).

    Args:
        league_id: The Sleeper league ID

    Returns:
        JSON response with league data
    """
    # Try to get from database first
    db_result = DatabaseManager.get_league_data(league_id)

    if db_result.get('status') == 'success':
        return jsonify({
            'status': 'success',
            'data': db_result,
            'source': 'database',
            'timestamp': datetime.now(UTC).isoformat()
        })

    # If not in database, fetch from API
    logger.info(
        "League not found in database, fetching from Sleeper API: %s", league_id)
    league_data = SleeperScraper.scrape_league_data(league_id)

    if not league_data.get('success'):
        return jsonify({
            'status': 'error',
            'error': 'Invalid league ID or failed to fetch league data',
            'details': league_data.get('error'),
            'league_id': league_id
        }), 404

    # Save to database
    save_result = DatabaseManager.save_league_data(league_data)

    if save_result.get('status') != 'success':
        logger.warning("Failed to save league data to database: %s",
                       save_result.get('error'))

    return jsonify({
        'status': 'success',
        'data': league_data,
        'source': 'sleeper_api',
        'database_saved': save_result.get('status') == 'success',
        'timestamp': datetime.now(UTC).isoformat()
    })


@api_bp.route('/sleeper/league/<string:league_id>/rosters', methods=['GET'])
@with_error_handling
def get_league_rosters(league_id: str):
    """
    Get league rosters data.

    Args:
        league_id: The Sleeper league ID

    Returns:
        JSON response with rosters data
    """
    # First try to get full league data (uses caching)
    league_result = DatabaseManager.get_league_data(league_id)

    if league_result.get('status') == 'success':
        return jsonify({
            'status': 'success',
            'league_id': league_id,
            'rosters': league_result['rosters'],
            'count': len(league_result['rosters']),
            'last_updated': league_result.get('last_updated'),
            'timestamp': datetime.now(UTC).isoformat()
        })

    # Fallback to direct API call if not in database
    rosters_data = SleeperScraper.fetch_league_rosters(league_id)

    if rosters_data is None:
        return jsonify({
            'status': 'error',
            'error': 'Invalid league ID or failed to fetch roster data',
            'league_id': league_id
        }), 404

    return jsonify({
        'status': 'success',
        'league_id': league_id,
        'rosters': rosters_data,
        'count': len(rosters_data),
        'source': 'direct_api',
        'timestamp': datetime.now(UTC).isoformat()
    })


@api_bp.route('/sleeper/league/<string:league_id>/users', methods=['GET'])
@with_error_handling
def get_league_users(league_id: str):
    """
    Get league users data.

    Args:
        league_id: The Sleeper league ID

    Returns:
        JSON response with users data
    """
    # First try to get full league data (uses caching)
    league_result = DatabaseManager.get_league_data(league_id)

    if league_result.get('status') == 'success':
        return jsonify({
            'status': 'success',
            'league_id': league_id,
            'users': league_result['users'],
            'count': len(league_result['users']),
            'last_updated': league_result.get('last_updated'),
            'timestamp': datetime.now(UTC).isoformat()
        })

    # Fallback to direct API call if not in database
    users_data = SleeperScraper.fetch_league_users(league_id)

    if users_data is None:
        return jsonify({
            'status': 'error',
            'error': 'Invalid league ID or failed to fetch users data',
            'league_id': league_id
        }), 404

    return jsonify({
        'status': 'success',
        'league_id': league_id,
        'users': users_data,
        'count': len(users_data),
        'source': 'direct_api',
        'timestamp': datetime.now(UTC).isoformat()
    })


@api_bp.route('/sleeper/league/<string:league_id>/refresh', methods=['POST'])
@with_error_handling
def refresh_league_data(league_id: str):
    """
    Manually refresh league data from Sleeper API.

    Args:  
        league_id: The Sleeper league ID

    Returns:
        JSON response with refresh results
    """
    logger.info("Manual refresh requested for league_id: %s", league_id)

    # Fetch fresh data from Sleeper API
    league_data = SleeperScraper.scrape_league_data(league_id)

    if not league_data.get('success'):
        return jsonify({
            'status': 'error',
            'error': 'Failed to refresh league data',
            'details': league_data.get('error'),
            'league_id': league_id
        }), 400

    # Save to database
    save_result = DatabaseManager.save_league_data(league_data)

    if save_result.get('status') != 'success':
        return jsonify({
            'status': 'error',
            'error': 'Failed to save refreshed league data',
            'details': save_result.get('error'),
            'league_id': league_id
        }), 500

    return jsonify({
        'status': 'success',
        'message': 'League data refreshed successfully',
        'league_id': league_id,
        'refresh_results': save_result,
        'timestamp': datetime.now(UTC).isoformat()
    })


# ============================================================================
# SLEEPER RESEARCH ENDPOINTS
# ============================================================================

@api_bp.route('/sleeper/players/research/<string:season>', methods=['GET'])
@with_error_handling
def get_research_data(season: str):
    """
    Get player research data for a specific season.

    Query parameters:
        week (int): Week number (default: 1)
        league_type (int): League type (default: 2 for dynasty)

    Args:
        season: The NFL season year (e.g., "2024")

    Returns:
        JSON response with research data
    """
    # Get query parameters
    week = int(request.args.get('week', 1))
    league_type = int(request.args.get('league_type', 2))

    # Try to get from database first
    db_result = DatabaseManager.get_research_data(season, week, league_type)

    if db_result.get('status') == 'success':
        return jsonify({
            'status': 'success',
            'data': db_result,
            'source': 'database',
            'timestamp': datetime.now(UTC).isoformat()
        })

    # If not in database, fetch from API
    logger.info(
        "Research data not found in database, fetching from Sleeper API: %s", season)
    research_data = SleeperScraper.scrape_research_data(
        season, week, league_type)

    if not research_data.get('success'):
        return jsonify({
            'status': 'error',
            'error': 'Failed to fetch research data',
            'details': research_data.get('error'),
            'season': season
        }), 404

    # Save to database
    save_result = DatabaseManager.save_research_data(research_data)

    if save_result.get('status') != 'success':
        logger.warning(
            "Failed to save research data to database: %s", save_result.get('error'))

    return jsonify({
        'status': 'success',
        'data': research_data,
        'source': 'sleeper_api',
        'database_saved': save_result.get('status') == 'success',
        'timestamp': datetime.now(UTC).isoformat()
    })


@api_bp.route('/sleeper/players/research/<string:season>/refresh', methods=['POST'])
@with_error_handling
def refresh_research_data(season: str):
    """
    Manually refresh research data from Sleeper API.

    Query parameters:
        week (int): Week number (default: 1)
        league_type (int): League type (default: 2 for dynasty)

    Args:
        season: The NFL season year (e.g., "2024")

    Returns:
        JSON response with refresh results
    """
    # Get query parameters
    week = int(request.args.get('week', 1))
    league_type = int(request.args.get('league_type', 2))

    logger.info(
        "Manual refresh requested for research data: season=%s, week=%s", season, week)

    # Fetch fresh data from Sleeper API
    research_data = SleeperScraper.scrape_research_data(
        season, week, league_type)

    if not research_data.get('success'):
        return jsonify({
            'status': 'error',
            'error': 'Failed to refresh research data',
            'details': research_data.get('error'),
            'season': season
        }), 400

    # Save to database
    save_result = DatabaseManager.save_research_data(research_data)

    if save_result.get('status') != 'success':
        return jsonify({
            'status': 'error',
            'error': 'Failed to save refreshed research data',
            'details': save_result.get('error'),
            'season': season
        }), 500

    return jsonify({
        'status': 'success',
        'message': 'Research data refreshed successfully',
        'season': season,
        'week': week,
        'league_type': league_type,
        'refresh_results': save_result,
        'timestamp': datetime.now(UTC).isoformat()
    })


# ============================================================================
# BULK REFRESH ENDPOINTS (for scheduled tasks)
# ============================================================================

@api_bp.route('/sleeper/refresh/all', methods=['POST'])
@with_error_handling
def refresh_all_data():
    """
    Refresh all stored data (useful for daily scheduled tasks).

    Query parameters:
        leagues (str): Comma-separated list of league IDs to refresh
        season (str): Season for research data refresh (default: current year)

    Returns:
        JSON response with comprehensive refresh results
    """
    # Get query parameters
    leagues_param = request.args.get('leagues', '')
    season = request.args.get('season', str(datetime.now().year))

    league_ids = [lid.strip() for lid in leagues_param.split(',')
                  if lid.strip()] if leagues_param else []

    logger.info("Bulk refresh requested - leagues: %s, season: %s",
                league_ids, season)

    results = {
        'status': 'success',
        'timestamp': datetime.now(UTC).isoformat(),
        'league_refreshes': [],
        'research_refresh': None,
        'errors': []
    }

    # Refresh league data
    for league_id in league_ids:
        try:
            league_data = SleeperScraper.scrape_league_data(league_id)
            if league_data.get('success'):
                save_result = DatabaseManager.save_league_data(league_data)

                results['league_refreshes'].append({
                    'league_id': league_id,
                    'status': 'success',
                    'save_result': save_result
                })
            else:
                results['errors'].append({
                    'type': 'league_refresh',
                    'league_id': league_id,
                    'error': league_data.get('error')
                })
        except Exception as e:
            logger.error("Error refreshing league %s: %s", league_id, e)
            results['errors'].append({
                'type': 'league_refresh',
                'league_id': league_id,
                'error': str(e)
            })

    # Refresh research data
    try:
        research_data = SleeperScraper.scrape_research_data(season)
        if research_data.get('success'):
            save_result = DatabaseManager.save_research_data(research_data)

            results['research_refresh'] = {
                'season': season,
                'status': 'success',
                'save_result': save_result
            }
        else:
            results['errors'].append({
                'type': 'research_refresh',
                'season': season,
                'error': research_data.get('error')
            })
    except Exception as e:
        logger.error(
            "Error refreshing research data for season %s: %s", season, e)
        results['errors'].append({
            'type': 'research_refresh',
            'season': season,
            'error': str(e)
        })

    # Set overall status based on errors
    if results['errors']:
        results['status'] = 'partial_success' if (
            results['league_refreshes'] or results['research_refresh']) else 'error'

    return jsonify(results)
