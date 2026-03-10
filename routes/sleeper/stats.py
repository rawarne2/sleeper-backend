from datetime import datetime, UTC
from flask import Blueprint, jsonify, request
from scrapers import SleeperScraper
from managers import DatabaseManager
from utils import setup_logging
from routes.helpers import with_error_handling

sleeper_stats_bp = Blueprint(
    'sleeper_stats', __name__, url_prefix='/api/sleeper/league')
logger = setup_logging()


@sleeper_stats_bp.route('/<string:league_id>/stats/seed', methods=['POST'])
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


@sleeper_stats_bp.route('/<string:league_id>/stats/week/<int:week>', methods=['GET'])
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


@sleeper_stats_bp.route('/<string:league_id>/stats/week/<int:week>', methods=['POST', 'PUT'])
@with_error_handling
def refresh_weekly_stats(league_id: str, week: int):
    """
    Refresh/Update weekly stats for a specific week
    ---
    tags:
      - Sleeper Weekly Stats
    summary: Refresh/Update weekly stats for a specific week
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
        'refreshed_stats': {
            'status': 'success',
            'data_type': 'weekly',
            'season': season,
            'week': week,
            'records': weekly_stats,
            'count': len(weekly_stats)
        },
        'timestamp': datetime.now(UTC).isoformat()
    })
