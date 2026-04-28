from datetime import datetime, UTC
from flask import Blueprint, jsonify, request
from managers.database_manager import DatabaseManager
from models.entities import SleeperLeague, SleeperLeagueStats
from services.daily_refresh import refresh_weekly_stats_for_league
from utils.helpers import setup_logging
from routes.helpers import with_error_handling

sleeper_stats_bp = Blueprint(
    'sleeper_stats', __name__, url_prefix='/api/sleeper/league')
logger = setup_logging()


@sleeper_stats_bp.route('/<string:league_id>/stats/seed', methods=['POST', 'PUT'])
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
    data = request.get_json(silent=True) or {}
    league_name = data.get('league_name')
    season = data.get('season')
    league_type = data.get('league_type')
    scoring_settings = data.get('scoring_settings')

    existing = SleeperLeagueStats.query.filter_by(league_id=league_id).first()

    if existing:
        league_name = league_name or existing.league_name
        season = season or existing.season
        league_type = league_type or existing.league_type or 'dynasty'
    else:
        if not league_name or not season:
            return jsonify({
                'status': 'error',
                'error': 'league_name and season are required for new leagues',
            }), 400
        league_type = league_type or 'dynasty'

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

    row = SleeperLeagueStats.query.filter_by(league_id=league_id).first()
    start_week = (row.last_week_updated or 0) + 1 if row else 1
    weeks_to_fetch = range(start_week, 19)

    weekly_summary = None
    if start_week <= 18:
        logger.info(
            "Auto-fetching weekly stats league=%s weeks=%s-18",
            league_id, start_week,
        )
        weekly_summary = refresh_weekly_stats_for_league(
            league_id, season, weeks=weeks_to_fetch, league_type=league_type,
        )

    refreshed_row = SleeperLeagueStats.query.filter_by(league_id=league_id).first()
    last_week = refreshed_row.last_week_updated if refreshed_row else 0

    return jsonify({
        'status': 'success',
        'message': 'League stats seeded successfully',
        'action': result.get('action'),
        'league_id': league_id,
        'league_name': league_name,
        'season': season,
        'last_week_updated': last_week,
        'weekly_stats': weekly_summary,
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
        description: Whether to return season averages (weeks 1-17; week 18 excluded)
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
    season = request.args.get('season')
    league_type = request.args.get('league_type')

    if not season or not league_type:
        existing = SleeperLeagueStats.query.filter_by(league_id=league_id).first()
        if existing:
            season = season or existing.season
            league_type = league_type or existing.league_type or 'dynasty'
        else:
            league_row = SleeperLeague.query.filter_by(league_id=league_id).first()
            season = season or (str(league_row.season) if league_row and league_row.season else None)
            league_type = league_type or 'dynasty'

    if not season:
        return jsonify({
            'status': 'error',
            'error': 'season is required (not found in DB for this league_id)',
        }), 400

    logger.info("Weekly stats refresh requested for league: %s, week: %s, season: %s",
                league_id, week, season)

    summary = refresh_weekly_stats_for_league(
        league_id, season, weeks=[week], league_type=league_type,
    )
    week_results = summary.get('weeks') or []
    week_entry = week_results[0] if week_results else {}
    errors = summary.get('errors') or []

    if errors:
        return jsonify({
            'status': 'error',
            'error': 'Failed to refresh weekly stats',
            'details': errors[0].get('error', 'Unknown error'),
        }), 500

    if week_entry.get('status') == 'no_data':
        return jsonify({
            'status': 'error',
            'error': 'Failed to fetch weekly matchups',
            'details': 'No matchup data returned from Sleeper API',
        }), 400

    if week_entry.get('status') == 'no_records':
        return jsonify({
            'status': 'error',
            'error': 'Failed to parse weekly matchups',
            'details': 'No player scoring records found in matchup data',
        }), 400

    refreshed_row = SleeperLeagueStats.query.filter_by(league_id=league_id).first()
    last_week = refreshed_row.last_week_updated if refreshed_row else None

    return jsonify({
        'status': 'success',
        'message': 'Weekly stats refreshed successfully',
        'league_id': league_id,
        'week': week,
        'season': season,
        'league_type': league_type,
        'last_week_updated': last_week,
        'refresh_results': week_entry,
        'timestamp': datetime.now(UTC).isoformat()
    })
