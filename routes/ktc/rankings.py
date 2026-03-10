from datetime import datetime, UTC
from flask import Blueprint, jsonify, request
from scrapers import KTCScraper
from managers import DatabaseManager, FileManager
from utils import (save_and_verify_database, perform_file_operations,
                   validate_parameters, setup_logging)
from scrapers import scrape_and_process_data
from routes.helpers import filter_players_by_format

ktc_rankings_bp = Blueprint('ktc_rankings', __name__, url_prefix='/api/ktc')
logger = setup_logging()


@ktc_rankings_bp.route('/refresh', methods=['POST', 'PUT'])
def refresh_rankings():
    """
    Refresh/Update KTC player rankings
    ---
    tags:
      - KTC Player Rankings
    summary: Refresh/Update KTC player rankings
    description: |
      POST: Create/populate KTC rankings data
      PUT: Update existing KTC rankings data

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
        filtered_players = filter_players_by_format(
            players_sorted, league_format, tep_level)

        # Return success response with filtered data (align with GET shape)
        return jsonify({
            'message': 'Rankings updated successfully',
            'timestamp': datetime.now(UTC).isoformat(),
            'database_success': True,
            'file_saved': file_saved,
            's3_uploaded': s3_uploaded,
            # GET-style echoes
            'is_redraft': is_redraft,
            'league_format': league_format,
            'tep_level': tep_level,
            'count': len(filtered_players),
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


@ktc_rankings_bp.route('/cleanup', methods=['POST'])
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


@ktc_rankings_bp.route('/rankings', methods=['GET'])
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
        players_data = filter_players_by_format(
            players, league_format, tep_level)

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
