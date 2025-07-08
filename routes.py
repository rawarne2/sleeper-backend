from datetime import datetime, UTC
from flask import Blueprint, jsonify, request

from models import db
from scrapers import SleeperScraper, KTCScraper
from managers import PlayerMerger, FileManager, DatabaseManager
from utils import (validate_refresh_parameters, scrape_and_process_data,
                   save_and_verify_database, perform_file_operations,
                   validate_parameters, BOOLEAN_STRINGS, setup_logging)

# Create a blueprint for routes
api_bp = Blueprint('api', __name__, url_prefix='/api')

logger = setup_logging()


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
