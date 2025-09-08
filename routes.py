from datetime import datetime, UTC
from flask import Blueprint, jsonify, request
from functools import wraps
import json

from scrapers import SleeperScraper, KTCScraper
from managers import FileManager, DatabaseManager
from utils import (save_and_verify_database, perform_file_operations,
                   validate_parameters, setup_logging)
from scrapers import scrape_and_process_data, scrape_and_save_all_ktc_data
from models import SleeperWeeklyData, db

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
    Refresh Sleeper player data and merge with existing KTC data
    ---
    tags:
      - Sleeper Players
    summary: Refresh Sleeper player data
    description: |
      Refresh Sleeper player data and merge with existing KTC data. Returns comprehensive player data including physical attributes, career info, fantasy data, injury status, and metadata. Merges with KTC players by name/position.

      **Performance Note**: This operation takes 30-60 seconds as it fetches from external APIs.
    responses:
      200:
        description: Sleeper data refreshed successfully
        schema:
          type: object
          properties:
            message:
              type: string
              example: 'Sleeper data refreshed and merged successfully'
            timestamp:
              type: string
              format: date-time
            sleeper_data_results:
              type: object
              properties:
                total_sleeper_players:
                  type: integer
                existing_records_before:
                  type: integer
                ktc_players_updated:
                  type: integer
                new_records_created:
                  type: integer
                match_failures:
                  type: integer
                total_processed:
                  type: integer
            database_success:
              type: boolean
            merge_effective:
              type: boolean
      500:
        description: Server error during Sleeper refresh
        schema:
          type: object
          properties:
            error:
              type: string
              example: 'Internal server error during Sleeper refresh'
            details:
              type: string
            database_success:
              type: boolean
              example: false
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

        # Save Sleeper data to database
        merge_result = DatabaseManager.save_sleeper_data_to_db(
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
    Refresh KTC player rankings
    ---
    tags:
      - KTC Player Rankings
    summary: Refresh KTC player rankings
    description: |
      Fetch fresh KTC rankings and store in database. Returns all player data including dynasty/redraft values, rankings, trends, and tiers.

      **Performance Note**: This operation takes 30-60 seconds as it fetches from external APIs.
    parameters:
      - name: is_redraft
        in: query
        description: Ranking type - 'true' for redraft (current season only), 'false' for dynasty (long-term player value)
        required: false
        type: string
        enum: ['true', 'false']
        default: 'false'
      - name: league_format
        in: query
        description: League format - '1qb' for standard leagues, 'superflex' for superflex leagues (can start 2 QBs)
        required: false
        type: string
        enum: ['1qb', 'superflex']
        default: '1qb'
      - name: tep_level
        in: query
        description: |
          TEP (Tight End Premium) scoring level:
          - '' (empty): Standard scoring
          - 'tep': +0.5 points per TE reception
          - 'tepp': +1.0 points per TE reception
          - 'teppp': +1.5 points per TE reception
        required: false
        type: string
        enum: ['', 'tep', 'tepp', 'teppp']
        default: ''
    responses:
      200:
        description: Rankings refreshed successfully
        schema:
          type: object
          properties:
            message:
              type: string
              example: 'Rankings refreshed successfully'
            timestamp:
              type: string
              format: date-time
            database_success:
              type: boolean
            file_saved:
              type: boolean
            s3_uploaded:
              type: boolean
            players:
              type: array
              items:
                type: object
                properties:
                  playerName:
                    type: string
                  position:
                    type: string
                    enum: ['QB', 'RB', 'WR', 'TE', 'K', 'DEF']
                  team:
                    type: string
                  ktc:
                    type: object
            operations_summary:
              type: object
              properties:
                players_count:
                  type: integer
                database_saved_count:
                  type: integer
                file_saved:
                  type: boolean
                s3_uploaded:
                  type: boolean
      400:
        description: Invalid parameters
        schema:
          type: object
          properties:
            error:
              type: string
              example: 'Invalid parameter value'
      500:
        description: Server error during refresh
        schema:
          type: object
          properties:
            error:
              type: string
              example: 'Internal server error during refresh'
            details:
              type: string
            database_success:
              type: boolean
              example: false
    """
    try:
        # Extract and validate parameters
        is_redraft_str = request.args.get('is_redraft', 'false')
        league_format_str = request.args.get('league_format', '1qb')
        tep_level_str = request.args.get('tep_level', '')

        valid, league_format, tep_level, error_msg = validate_parameters(
            is_redraft_str, league_format_str, tep_level_str)
        if not valid:
            return jsonify({'error': error_msg}), 400

        is_redraft = is_redraft_str.lower() == 'true'
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
            DatabaseManager, players_sorted, league_format, is_redraft)
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

        # Filter players based on league_format for response
        filtered_players = []
        for player in players_sorted:
            # Always use to_dict() method for consistent structure
            player_dict = player.to_dict()

            if league_format == 'superflex':
                # Only include players with superflex values
                if player_dict.get('ktc', {}).get('superflexValues'):
                    # Remove oneQB values from response
                    if 'ktc' in player_dict and player_dict['ktc']:
                        player_dict['ktc']['oneQBValues'] = None
                    filtered_players.append(player_dict)
            else:  # 1qb
                # Only include players with oneQB values
                if player_dict.get('ktc', {}).get('oneQBValues'):
                    # Remove superflex values from response
                    if 'ktc' in player_dict and player_dict['ktc']:
                        player_dict['ktc']['superflexValues'] = None
                    filtered_players.append(player_dict)

        # Return success response with filtered data
        return jsonify({
            'message': 'Rankings refreshed successfully',
            'timestamp': datetime.now(UTC).isoformat(),
            'database_success': True,
            'file_saved': file_saved,
            's3_uploaded': s3_uploaded,
            'players': filtered_players,
            'operations_summary': {
                'players_count': len(filtered_players),
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
    Database health check endpoint
    ---
    tags:
      - Health
    summary: Check API and database health status
    description: Check API and database health status. Returns service status and database connection info.
    responses:
      200:
        description: Service is healthy
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['healthy']
              example: 'healthy'
            database:
              type: string
              enum: ['connected']
              example: 'connected'
            timestamp:
              type: string
              format: date-time
              example: '2025-01-05T17:58:12.123456+00:00'
      500:
        description: Service is unhealthy
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['unhealthy']
              example: 'unhealthy'
            database:
              type: string
              enum: ['connection_failed', 'error']
              example: 'connection_failed'
            error:
              type: string
              example: 'Database connection timeout'
            timestamp:
              type: string
              format: date-time
              example: '2025-01-05T17:58:12.123456+00:00'
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
    Clean up incomplete or corrupted data
    ---
    tags:
      - KTC Player Rankings
    summary: Clean up incomplete data
    description: Endpoint to clean up incomplete or corrupted data from the database
    parameters:
      - name: is_redraft
        in: query
        description: Ranking type - 'true' for redraft, 'false' for dynasty
        required: false
        type: string
        enum: ['true', 'false']
        default: 'false'
      - name: league_format
        in: query
        description: League format - '1qb' or 'superflex'
        required: false
        type: string
        enum: ['1qb', 'superflex']
        default: '1qb'
      - name: tep_level
        in: query
        description: TEP scoring level - '', 'tep', 'tepp', or 'teppp'
        required: false
        type: string
        enum: ['', 'tep', 'tepp', 'teppp']
        default: ''
    responses:
      200:
        description: Cleanup completed successfully
        schema:
          type: object
          properties:
            message:
              type: string
              example: 'Database cleanup completed'
            timestamp:
              type: string
              format: date-time
            cleanup_result:
              type: object
              properties:
                status:
                  type: string
                records_removed:
                  type: integer
                configuration:
                  type: object
      400:
        description: Invalid parameters
        schema:
          type: object
          properties:
            error:
              type: string
              example: 'Invalid parameter value'
      500:
        description: Server error during cleanup
        schema:
          type: object
          properties:
            error:
              type: string
              example: 'Internal server error during cleanup'
            details:
              type: string
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

        is_redraft = is_redraft_str.lower() == 'true'

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
    Get stored player rankings
    ---
    tags:
      - KTC Player Rankings
    summary: Get stored player rankings
    description: |
      Retrieve stored player rankings with filtering options. Returns comprehensive player data including KTC rankings, Sleeper data, physical attributes, career info, and injury status.

      **Performance Note**: Served from database cache, typically < 1 second response time.
    parameters:
      - name: is_redraft
        in: query
        description: Ranking type - 'true' for redraft (current season only), 'false' for dynasty (long-term player value)
        required: false
        type: string
        enum: ['true', 'false']
        default: 'false'
      - name: league_format
        in: query
        description: League format - '1qb' for standard leagues, 'superflex' for superflex leagues (can start 2 QBs)
        required: false
        type: string
        enum: ['1qb', 'superflex']
        default: '1qb'
      - name: tep_level
        in: query
        description: |
          TEP (Tight End Premium) scoring level:
          - '' (empty): Standard scoring
          - 'tep': +0.5 points per TE reception
          - 'tepp': +1.0 points per TE reception
          - 'teppp': +1.5 points per TE reception
        required: false
        type: string
        enum: ['', 'tep', 'tepp', 'teppp']
        default: ''
    responses:
      200:
        description: Rankings retrieved successfully
        schema:
          type: object
          properties:
            timestamp:
              type: string
              format: date-time
            is_redraft:
              type: boolean
            league_format:
              type: string
              enum: ['1qb', 'superflex']
            tep_level:
              type: string
              enum: ['', 'tep', 'tepp', 'teppp']
            count:
              type: integer
            players:
              type: array
              items:
                type: object
                properties:
                  playerName:
                    type: string
                  position:
                    type: string
                    enum: ['QB', 'RB', 'WR', 'TE', 'K', 'DEF']
                  team:
                    type: string
                  sleeper_player_id:
                    type: string
                  birth_date:
                    type: string
                    format: date
                  height:
                    type: string
                  weight:
                    type: string
                  college:
                    type: string
                  years_exp:
                    type: integer
                  injury_status:
                    type: string
                  ktc:
                    type: object
      400:
        description: Invalid parameters
        schema:
          type: object
          properties:
            error:
              type: string
              example: 'Invalid parameter value'
      404:
        description: No rankings found for specified parameters
        schema:
          type: object
          properties:
            error:
              type: string
              example: 'No rankings found for the specified parameters'
            suggestion:
              type: string
              example: 'Try calling the /api/ktc/refresh/all endpoint first to populate data'
            parameters:
              type: object
      500:
        description: Server error during retrieval
        schema:
          type: object
          properties:
            error:
              type: string
              example: 'Internal server error during rankings retrieval'
            details:
              type: string
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

        is_redraft = is_redraft_str.lower() == 'true'

        # Query the database - get all players regardless of format since we store both
        players, last_updated = DatabaseManager.get_players_from_db(
            league_format)

        if not players:
            return jsonify({
                'error': 'No rankings found for the specified parameters',
                'suggestion': 'Try calling the /api/ktc/refresh/all endpoint first to populate data',
                'parameters': {
                    'is_redraft': is_redraft,
                    'league_format': league_format,
                    'tep_level': tep_level
                }
            }), 404

        # Convert players to dict format and filter based on league_format and tep_level
        players_data = []
        for player in players:
            player_dict = player.to_dict()

            # Filter KTC values based on league_format parameter and apply TEP filtering
            if league_format == 'superflex':
                # Only include superflex values, remove oneQB values
                if player_dict.get('ktc', {}).get('superflexValues'):
                    player_dict['ktc']['oneQBValues'] = None

                    # Apply TEP level filtering to superflex values
                    superflex_values = player_dict['ktc']['superflexValues']
                    if tep_level and superflex_values:
                        # Use TEP-specific values if requested and available
                        if tep_level == 'tep' and superflex_values.get('tep', {}).get('value'):
                            superflex_values['value'] = superflex_values['tep']['value']
                            superflex_values['rank'] = superflex_values['tep']['rank']
                            superflex_values['positionalRank'] = superflex_values['tep']['positionalRank']
                            superflex_values['overallTier'] = superflex_values['tep']['overallTier']
                            superflex_values['positionalTier'] = superflex_values['tep']['positionalTier']
                        elif tep_level == 'tepp' and superflex_values.get('tepp', {}).get('value'):
                            superflex_values['value'] = superflex_values['tepp']['value']
                            superflex_values['rank'] = superflex_values['tepp']['rank']
                            superflex_values['positionalRank'] = superflex_values['tepp']['positionalRank']
                            superflex_values['overallTier'] = superflex_values['tepp']['overallTier']
                            superflex_values['positionalTier'] = superflex_values['tepp']['positionalTier']
                        elif tep_level == 'teppp' and superflex_values.get('teppp', {}).get('value'):
                            superflex_values['value'] = superflex_values['teppp']['value']
                            superflex_values['rank'] = superflex_values['teppp']['rank']
                            superflex_values['positionalRank'] = superflex_values['teppp']['positionalRank']
                            superflex_values['overallTier'] = superflex_values['teppp']['overallTier']
                            superflex_values['positionalTier'] = superflex_values['teppp']['positionalTier']

                    players_data.append(player_dict)
            else:  # 1qb
                # Only include oneQB values, remove superflex values
                if player_dict.get('ktc', {}).get('oneQBValues'):
                    player_dict['ktc']['superflexValues'] = None

                    # Apply TEP level filtering to oneQB values
                    oneqb_values = player_dict['ktc']['oneQBValues']
                    if tep_level and oneqb_values:
                        # Use TEP-specific values if requested and available
                        if tep_level == 'tep' and oneqb_values.get('tep', {}).get('value'):
                            oneqb_values['value'] = oneqb_values['tep']['value']
                            oneqb_values['rank'] = oneqb_values['tep']['rank']
                            oneqb_values['positionalRank'] = oneqb_values['tep']['positionalRank']
                            oneqb_values['overallTier'] = oneqb_values['tep']['overallTier']
                            oneqb_values['positionalTier'] = oneqb_values['tep']['positionalTier']
                        elif tep_level == 'tepp' and oneqb_values.get('tepp', {}).get('value'):
                            oneqb_values['value'] = oneqb_values['tepp']['value']
                            oneqb_values['rank'] = oneqb_values['tepp']['rank']
                            oneqb_values['positionalRank'] = oneqb_values['tepp']['positionalRank']
                            oneqb_values['overallTier'] = oneqb_values['tepp']['overallTier']
                            oneqb_values['positionalTier'] = oneqb_values['tepp']['positionalTier']
                        elif tep_level == 'teppp' and oneqb_values.get('teppp', {}).get('value'):
                            oneqb_values['value'] = oneqb_values['teppp']['value']
                            oneqb_values['rank'] = oneqb_values['teppp']['rank']
                            oneqb_values['positionalRank'] = oneqb_values['teppp']['positionalRank']
                            oneqb_values['overallTier'] = oneqb_values['teppp']['overallTier']
                            oneqb_values['positionalTier'] = oneqb_values['teppp']['positionalTier']

                    players_data.append(player_dict)

        return jsonify({
            'timestamp': last_updated.isoformat() if last_updated else None,
            'is_redraft': is_redraft,
            'league_format': league_format,
            'tep_level': tep_level,
            'count': len(players_data),
            'players': players_data
        })

    except Exception as e:
        logger.error("Error retrieving rankings: %s", e)
        return jsonify({
            'error': 'Internal server error during rankings retrieval',
            'details': str(e)
        }), 500


@api_bp.route('/ktc/refresh/all', methods=['POST'])
@with_error_handling
def refresh_ktc_all():
    """
    Comprehensive KTC refresh
    ---
    tags:
      - Bulk Operations
    summary: Comprehensive KTC refresh
    description: |
      All KTC refresh - scrapes and saves ALL KTC data. Gets dynasty + redraft data with all league formats (1QB + Superflex) and all TEP levels (base, TEP, TEPP, TEPPP) in a single operation.

      **Ideal for cron jobs** since it ensures complete data coverage without needing multiple calls with different parameters.

      **Performance Note**: This is a comprehensive operation that may take several minutes to complete.

      No query parameters needed - this is truly comprehensive!
    responses:
      200:
        description: Comprehensive refresh completed successfully
        schema:
          type: object
          properties:
            message:
              type: string
              example: 'Comprehensive refresh completed successfully'
            timestamp:
              type: string
              format: date-time
            results:
              type: object
              properties:
                overall_status:
                  type: string
                  enum: ['success', 'partial_success', 'error']
                dynasty:
                  type: object
                  properties:
                    status:
                      type: string
                    players_count:
                      type: integer
                    db_count:
                      type: integer
                redraft:
                  type: object
                  properties:
                    status:
                      type: string
                    players_count:
                      type: integer
                    db_count:
                      type: integer
            summary:
              type: object
              properties:
                dynasty_players:
                  type: integer
                dynasty_saved:
                  type: integer
                redraft_players:
                  type: integer
                redraft_saved:
                  type: integer
                total_players:
                  type: integer
                total_saved:
                  type: integer
      500:
        description: Server error during comprehensive refresh
        schema:
          type: object
          properties:
            error:
              type: string
              example: 'Internal server error during comprehensive refresh'
            details:
              type: string
    """
    try:
        # Verify database connection
        logger.info(
            "Verifying database connection before comprehensive refresh...")
        if not DatabaseManager.verify_database_connection():
            return jsonify({
                'error': 'Database connection failed',
                'details': 'Cannot establish database connection before starting refresh operation'
            }), 500

        # Scrape and save all KTC data
        logger.info(
            "Starting comprehensive KTC refresh for all formats and TEP levels...")

        results = scrape_and_save_all_ktc_data(KTCScraper, DatabaseManager)

        # Return results
        if results['overall_status'] == 'error':
            return jsonify({
                'error': 'Comprehensive refresh failed',
                'details': results.get('error', 'Both dynasty and redraft operations failed'),
                'results': results
            }), 500
        elif results['overall_status'] == 'partial_success':
            return jsonify({
                'message': 'Comprehensive refresh partially successful',
                'warning': 'One of the operations failed',
                'timestamp': datetime.now(UTC).isoformat(),
                'results': results
            }), 200
        else:
            return jsonify({
                'message': 'Comprehensive refresh completed successfully',
                'timestamp': datetime.now(UTC).isoformat(),
                'results': results,
                'summary': {
                    'dynasty_players': results['dynasty']['players_count'],
                    'dynasty_saved': results['dynasty']['db_count'],
                    'redraft_players': results['redraft']['players_count'],
                    'redraft_saved': results['redraft']['db_count'],
                    'total_players': results['dynasty']['players_count'] + results['redraft']['players_count'],
                    'total_saved': results['dynasty']['db_count'] + results['redraft']['db_count']
                }
            })

    except Exception as e:
        logger.error("Error in comprehensive KTC refresh: %s", e)
        return jsonify({
            'error': 'Internal server error during comprehensive refresh',
            'details': str(e)
        }), 500


# ============================================================================
# SLEEPER LEAGUE ENDPOINTS
# ============================================================================

@api_bp.route('/sleeper/league/<string:league_id>', methods=['GET'])
@with_error_handling
def get_league_data(league_id: str):
    """
    Get comprehensive league data
    ---
    tags:
      - Sleeper Leagues
    summary: Get comprehensive league data
    description: |
      Get comprehensive league data (league info, rosters, users). Returns complete league configuration, all rosters with player IDs, and user information. Checks database first, falls back to Sleeper API.
    parameters:
      - name: league_id
        in: path
        description: The Sleeper league ID
        required: true
        type: string
        pattern: '^[0-9]+$'
    responses:
      200:
        description: League data retrieved successfully
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['success']
            data:
              type: object
              properties:
                league:
                  type: object
                  properties:
                    league_id:
                      type: string
                    name:
                      type: string
                    season:
                      type: string
                      type: integer
                    status:
                      type: string
                rosters:
                  type: array
                  items:
                    type: object
                    properties:
                      roster_id:
                        type: integer
                      owner_id:
                        type: string
                      players:
                        type: array
                        items:
                          type: string
                users:
                  type: array
                  items:
                    type: object
                    properties:
                      user_id:
                        type: string
                      username:
                        type: string
                      display_name:
                        type: string
            source:
              type: string
              enum: ['database', 'sleeper_api']
            database_saved:
              type: boolean
            timestamp:
              type: string
              format: date-time
      404:
        description: League not found
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['error']
            error:
              type: string
              example: 'Invalid league ID or failed to fetch league data'
            details:
              type: string
            league_id:
              type: string
      500:
        description: Server error
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['error']
            error:
              type: string
            details:
              type: string
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

    # If not in database, fetch from Sleeper API
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
    Get league rosters
    ---
    tags:
      - Sleeper Leagues
    summary: Get league rosters
    description: Get league rosters data for all teams in the league
    parameters:
      - name: league_id
        in: path
        description: The Sleeper league ID
        required: true
        type: string
        pattern: '^[0-9]+$'
    responses:
      200:
        description: Rosters retrieved successfully
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['success']
            league_id:
              type: string
            rosters:
              type: array
              items:
                type: object
                properties:
                  roster_id:
                    type: integer
                  owner_id:
                    type: string
                  players:
                    type: array
                    items:
                      type: string
            count:
              type: integer
            timestamp:
              type: string
              format: date-time
      404:
        description: League not found
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['error']
            error:
              type: string
            league_id:
              type: string
      500:
        description: Server error
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['error']
            error:
              type: string
            details:
              type: string
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
    Get league users
    ---
    tags:
      - Sleeper Leagues
    summary: Get league users
    description: Get league users data for all participants in the league
    parameters:
      - name: league_id
        in: path
        description: The Sleeper league ID
        required: true
        type: string
        pattern: '^[0-9]+$'
    responses:
      200:
        description: Users retrieved successfully
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['success']
            league_id:
              type: string
            users:
              type: array
              items:
                type: object
                properties:
                  user_id:
                    type: string
                  username:
                    type: string
                  display_name:
                    type: string
                  avatar:
                    type: string
                  team_name:
                    type: string
            count:
              type: integer
            last_updated:
              type: string
              format: date-time
            timestamp:
              type: string
              format: date-time
      404:
        description: League not found
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['error']
            error:
              type: string
            league_id:
              type: string
      500:
        description: Server error
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['error']
            error:
              type: string
            details:
              type: string
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
    Refresh league data
    ---
    tags:
      - Sleeper Leagues
    summary: Refresh league data
    description: Refresh all league data from Sleeper API (league info, rosters, users)
    parameters:
      - name: league_id
        in: path
        description: The Sleeper league ID
        required: true
        type: string
        pattern: '^[0-9]+$'
    responses:
      200:
        description: League data refreshed successfully
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['success', 'partial_success', 'error']
            timestamp:
              type: string
              format: date-time
            league_id:
              type: string
            league_data:
              type: object
              properties:
                status:
                  type: string
                save_result:
                  type: object
            users_data:
              type: object
              properties:
                status:
                  type: string
                message:
                  type: string
            rosters_data:
              type: object
              properties:
                status:
                  type: string
                message:
                  type: string
            errors:
              type: array
              items:
                type: object
                properties:
                  type:
                    type: string
                  error:
                    type: string
      404:
        description: League not found
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['error']
            error:
              type: string
            league_id:
              type: string
      500:
        description: Server error
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['error']
            error:
              type: string
            details:
              type: string
    """
    logger.info("League data refresh requested for league_id: %s", league_id)

    results = {
        'status': 'success',
        'timestamp': datetime.now(UTC).isoformat(),
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
            results['league_data'] = {
                'status': 'success',
                'save_result': save_result
            }
            logger.info(
                "Successfully refreshed league data for league_id: %s", league_id)
        else:
            results['errors'].append({
                'type': 'league_data',
                'error': league_data.get('error')
            })
            results['league_data'] = {'status': 'error'}

        logger.info(
            "League data refresh completed for league_id: %s", league_id)
        results['users_data'] = {'status': 'not_implemented',
                                 'message': 'Users refresh not yet implemented'}
        results['rosters_data'] = {
            'status': 'not_implemented', 'message': 'Rosters refresh not yet implemented'}

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

    return jsonify(results)


# ============================================================================
# SLEEPER RESEARCH ENDPOINTS
# ============================================================================

@api_bp.route('/sleeper/players/research/<string:season>', methods=['GET'])
@with_error_handling
def get_research_data(season: str):
    """
    Get player research data
    ---
    tags:
      - Sleeper Research
    summary: Get player research data
    description: |
      Get player research data for a specific season. Returns comprehensive research metrics including rankings, projections, performance data, and statistical analysis. Checks database first.
    parameters:
      - name: season
        in: path
        description: The NFL season year
        required: true
        type: string
        pattern: '^[0-9]{4}$'
      - name: week
        in: query
        description: Week number (1-18 for regular season)
        required: false
        type: integer
        minimum: 1
        maximum: 22
        default: 1
      - name: league_type
        in: query
        description: League type
        required: false
        type: string
        enum: ['dynasty', 'redraft']
        default: 'dynasty'
    responses:
      200:
        description: Research data retrieved successfully
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['success']
            data:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                  season:
                    type: string
                  week:
                    type: integer
                  league_type:
                    type: integer
                  player_id:
                    type: string
                  research_data:
                    type: object
                    description: Research metrics and analytics data
                  last_updated:
                    type: string
                    format: date-time
            source:
              type: string
              enum: ['database', 'sleeper_api']
            database_saved:
              type: boolean
            timestamp:
              type: string
              format: date-time
      404:
        description: Research data not found
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['error']
            error:
              type: string
              example: 'Failed to fetch research data'
            details:
              type: string
            season:
              type: string
      500:
        description: Server error
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['error']
            error:
              type: string
            details:
              type: string
    """
    # Get query parameters
    week = int(request.args.get('week', 1))
    league_type = request.args.get('league_type', 'dynasty')

    logger.info(
        "Research data requested for season: %s, week: %s", season, week)

    # Check database first
    research_records = SleeperWeeklyData.query.filter_by(
        season=season,
        week=week,
        league_type=league_type
    ).all()

    if research_records:
        logger.info("Found %s research records in database",
                    len(research_records))
        return jsonify({
            'status': 'success',
            'data': [record.to_dict() for record in research_records],
            'source': 'database',
            'database_saved': True,
            'timestamp': datetime.now(UTC).isoformat()
        })

    # If not in database, try to fetch from Sleeper API
    logger.info(
        "No research data found in database, fetching from Sleeper API...")
    research_data = SleeperScraper.scrape_research_data(
        season, week, league_type)

    if not research_data.get('success'):
        return jsonify({
            'status': 'error',
            'error': 'Failed to fetch research data',
            'details': research_data.get('error', 'Unknown error'),
            'season': season
        }), 404

    return jsonify({
        'status': 'success',
        'data': research_data.get('research_data', []),
        'source': 'sleeper_api',
        'database_saved': False,
        'timestamp': datetime.now(UTC).isoformat()
    })


@api_bp.route('/sleeper/players/research/<string:season>/refresh', methods=['POST'])
@with_error_handling
def refresh_research_data(season: str):
    """
    Refresh research data
    ---
    tags:
      - Sleeper Research
    summary: Refresh research data
    description: Manually refresh research data from Sleeper API for a specific season
    parameters:
      - name: season
        in: path
        description: The NFL season year
        required: true
        type: string
        pattern: '^[0-9]{4}$'
      - name: week
        in: query
        description: Week number (1-18 for regular season)
        required: false
        type: integer
        minimum: 1
        maximum: 22
        default: 1
      - name: league_type
        in: query
        description: League type
        required: false
        type: string
        enum: ['dynasty', 'redraft']
        default: 'dynasty'
    responses:
      200:
        description: Research data refreshed successfully
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['success']
            message:
              type: string
              example: 'Research data refreshed successfully'
            season:
              type: string
            week:
              type: integer
            league_type:
              type: integer
            refresh_results:
              type: object
            timestamp:
              type: string
              format: date-time
      400:
        description: Invalid parameters or failed to refresh
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['error']
            error:
              type: string
              example: 'Failed to refresh research data'
            details:
              type: string
            season:
              type: string
      500:
        description: Server error
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['error']
            error:
              type: string
              example: 'Failed to save refreshed research data'
            details:
              type: string
            season:
              type: string
    """
    # Get query parameters
    week = int(request.args.get('week', 1))
    league_type = request.args.get('league_type', 'dynasty')

    logger.info(
        "Manual refresh requested for research data: season=%s, week=%s", season, week)

    # Fetch fresh data from Sleeper API
    research_data = SleeperScraper.scrape_research_data(
        season, week, league_type)

    if not research_data.get('success'):
        return jsonify({
            'status': 'error',
            'error': 'Failed to refresh research data',
            'details': research_data.get('error', 'Unknown error'),
            'season': season
        }), 400

    # Save to database
    try:
        # Clear existing records for this season/week/league_type
        SleeperWeeklyData.query.filter_by(
            season=season,
            week=week,
            league_type=league_type
        ).delete()

        # Save new records
        saved_count = 0
        for player_id, player_data in research_data.get('research_data', {}).items():
            try:
                new_record = SleeperWeeklyData(
                    season=season,
                    week=week,
                    league_type=league_type,
                    player_id=player_id,
                    research_data=json.dumps(player_data)
                )
                db.session.add(new_record)
                saved_count += 1
            except Exception as e:
                logger.error(
                    "Error saving research record for player %s: %s", player_id, e)
                continue

        db.session.commit()

        return jsonify({
            'status': 'success',
            'message': 'Research data refreshed successfully',
            'season': season,
            'week': week,
            'league_type': league_type,
            'refresh_results': {
                'saved_count': saved_count,
                'total_players': len(research_data.get('research_data', {}))
            },
            'timestamp': datetime.now(UTC).isoformat()
        })

    except Exception as e:
        db.session.rollback()
        logger.error("Error saving refreshed research data: %s", e)
        return jsonify({
            'status': 'error',
            'error': 'Failed to save refreshed research data',
            'details': str(e),
            'season': season
        }), 500


# ============================================================================
# SLEEPER WEEKLY STATS ENDPOINTS
# ============================================================================

@api_bp.route('/sleeper/league/<string:league_id>/stats/seed', methods=['POST'])
@with_error_handling
def seed_league_stats(league_id: str):
    """
    Seed league stats information
    ---
    tags:
      - Sleeper Weekly Stats
    summary: Seed league stats information
    description: |
      Seed or update league information needed for weekly stats functionality.
      This endpoint should be called once per league before fetching weekly stats.
    parameters:
      - name: league_id
        in: path
        description: The Sleeper league ID
        required: true
        type: string
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            properties:
              league_name:
                type: string
                description: The league name
                example: "My Fantasy League"
              season:
                type: string
                description: The NFL season year
                pattern: '^[0-9]{4}$'
                example: "2024"
              league_type:
                type: string
                description: League type
                enum: ['dynasty', 'redraft']
                default: 'dynasty'
                example: 'dynasty'
              scoring_settings:
                type: string
                description: League scoring settings as JSON string (optional)
                example: '{"pass_yd": 0.04, "pass_td": 4}'
            required:
              - league_name
              - season
    responses:
      200:
        description: League stats seeded successfully
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['success']
            message:
              type: string
              example: 'League stats seeded successfully'
            action:
              type: string
              enum: ['created', 'updated']
            league_id:
              type: string
            league_name:
              type: string
            season:
              type: string
            timestamp:
              type: string
              format: date-time
      400:
        description: Invalid request data
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['error']
            error:
              type: string
              example: 'Missing required fields'
            details:
              type: string
      500:
        description: Server error
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['error']
            error:
              type: string
            details:
              type: string
    """
    # Get request data
    data = request.get_json()

    if not data:
        return jsonify({
            'status': 'error',
            'error': 'No JSON data provided'
        }), 400

    # Validate required fields
    league_name = data.get('league_name')
    season = data.get('season')

    if not league_name or not season:
        return jsonify({
            'status': 'error',
            'error': 'Missing required fields: league_name and season are required'
        }), 400

    # Get optional fields
    league_type = data.get('league_type', 'dynasty')
    scoring_settings = data.get('scoring_settings')

    logger.info("Seeding league stats for league: %s, season: %s, type: %s",
                league_id, season, league_type)

    # Use DatabaseManager to seed league stats
    result = DatabaseManager.seed_league_stats(
        league_id=league_id,
        league_name=league_name,
        season=season,
        league_type=league_type,
        scoring_settings=scoring_settings
    )

    if result.get('status') == 'error':
        return jsonify({
            'status': 'error',
            'error': 'Failed to seed league stats',
            'details': result.get('error', 'Unknown error')
        }), 500

    return jsonify({
        'status': 'success',
        'message': 'League stats seeded successfully',
        'action': result.get('action'),
        'league_id': league_id,
        'league_name': league_name,
        'season': season,
        'timestamp': datetime.now(UTC).isoformat()
    })


@api_bp.route('/sleeper/league/<string:league_id>/stats/week/<int:week>', methods=['GET'])
@with_error_handling
def get_weekly_stats(league_id: str, week: int):
    """
    Get weekly stats for a specific week
    ---
    tags:
      - Sleeper Weekly Stats
    summary: Get weekly stats for a specific week
    description: |
      Get weekly fantasy points and roster information for all players in a specific week.
      Returns player scoring data including points, roster ID, and starter status.
    parameters:
      - name: league_id
        in: path
        description: The Sleeper league ID
        required: true
        type: string
      - name: week
        in: path
        description: The week number
        required: true
        type: integer
        minimum: 1
        maximum: 18
      - name: season
        in: query
        description: The NFL season year
        required: false
        type: string
        pattern: '^[0-9]{4}$'
        default: '2024'
      - name: league_type
        in: query
        description: League type
        required: false
        type: string
        enum: ['dynasty', 'redraft']
        default: 'dynasty'
      - name: average
        in: query
        description: Whether to return season averages (weeks 1-16 only)
        required: false
        type: boolean
        default: false
    responses:
      200:
        description: Weekly stats retrieved successfully
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['success']
            data_type:
              type: string
              enum: ['weekly', 'averages']
            season:
              type: string
            week:
              type: integer
            records:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                  season:
                    type: string
                  week:
                    type: integer
                  league_type:
                    type: integer
                  player_id:
                    type: string
                  points:
                    type: number
                    format: float
                  roster_id:
                    type: integer
                  is_starter:
                    type: boolean
                  last_updated:
                    type: string
                    format: date-time
            count:
              type: integer
            timestamp:
              type: string
              format: date-time
      404:
        description: Weekly stats not found
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['error']
            error:
              type: string
              example: 'No weekly stats found for the specified parameters'
            details:
              type: string
      500:
        description: Server error
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['error']
            error:
              type: string
            details:
              type: string
    """
    # Get query parameters
    season = request.args.get('season', '2024')
    league_type = request.args.get('league_type', 'dynasty')
    average = request.args.get('average', 'false').lower() == 'true'

    logger.info("Weekly stats requested for league: %s, week: %s, season: %s, average: %s",
                league_id, week, season, average)

    # Get stats from database
    stats_result = DatabaseManager.get_weekly_stats(
        season=season,
        week=week if not average else None,
        league_type=league_type,
        average=average
    )

    if stats_result.get('status') == 'error':
        return jsonify({
            'status': 'error',
            'error': 'Failed to retrieve weekly stats',
            'details': stats_result.get('error', 'Unknown error')
        }), 500

    return jsonify({
        **stats_result,
        'timestamp': datetime.now(UTC).isoformat()
    })


@api_bp.route('/sleeper/league/<string:league_id>/stats/week/<int:week>/refresh', methods=['POST'])
@with_error_handling
def refresh_weekly_stats(league_id: str, week: int):
    """
    Refresh weekly stats for a specific week
    ---
    tags:
      - Sleeper Weekly Stats
    summary: Refresh weekly stats for a specific week
    description: |
      Fetch fresh weekly stats data from Sleeper API for a specific week and save to database.
      This endpoint fetches matchup data and extracts player scoring information.
    parameters:
      - name: league_id
        in: path
        description: The Sleeper league ID
        required: true
        type: string
      - name: week
        in: path
        description: The week number
        required: true
        type: integer
        minimum: 1
        maximum: 18
      - name: season
        in: query
        description: The NFL season year
        required: false
        type: string
        pattern: '^[0-9]{4}$'
        default: '2024'
      - name: league_type
        in: query
        description: League type
        required: false
        type: string
        enum: ['dynasty', 'redraft']
        default: 'dynasty'
    responses:
      200:
        description: Weekly stats refreshed successfully
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['success']
            message:
              type: string
              example: 'Weekly stats refreshed successfully'
            league_id:
              type: string
            week:
              type: integer
            season:
              type: string
            refresh_results:
              type: object
              properties:
                saved_count:
                  type: integer
                updated_count:
                  type: integer
                errors:
                  type: integer
                total_processed:
                  type: integer
            timestamp:
              type: string
              format: date-time
      400:
        description: Invalid parameters or failed to refresh
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['error']
            error:
              type: string
              example: 'Failed to refresh weekly stats'
            details:
              type: string
      500:
        description: Server error
        schema:
          type: object
          properties:
            status:
              type: string
              enum: ['error']
            error:
              type: string
            details:
              type: string
    """
    # Get query parameters
    season = request.args.get('season', '2024')
    league_type = request.args.get('league_type', 'dynasty')

    logger.info("Weekly stats refresh requested for league: %s, week: %s, season: %s",
                league_id, week, season)

    # Fetch fresh data from Sleeper API
    matchups_data = SleeperScraper.fetch_weekly_matchups(league_id, week)

    if not matchups_data:
        return jsonify({
            'status': 'error',
            'error': 'Failed to fetch weekly matchups',
            'details': 'No matchup data returned from Sleeper API'
        }), 400

    # Parse the matchup data to extract player scoring records
    weekly_stats = SleeperScraper.parse_weekly_matchups(matchups_data)

    if not weekly_stats:
        return jsonify({
            'status': 'error',
            'error': 'Failed to parse weekly matchups',
            'details': 'No player scoring records found in matchup data'
        }), 400

    # Save to database
    save_result = DatabaseManager.save_weekly_stats(
        weekly_stats, season, week, league_type
    )

    if save_result.get('status') == 'error':
        return jsonify({
            'status': 'error',
            'error': 'Failed to save weekly stats',
            'details': save_result.get('error', 'Unknown error')
        }), 500

    return jsonify({
        'status': 'success',
        'message': 'Weekly stats refreshed successfully',
        'league_id': league_id,
        'week': week,
        'season': season,
        'refresh_results': save_result,
        'timestamp': datetime.now(UTC).isoformat()
    })


# ============================================================================
# BULK REFRESH ENDPOINTS (for scheduled tasks)
# ============================================================================
