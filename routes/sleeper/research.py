from datetime import datetime, UTC
from flask import Blueprint, jsonify, request
import json
from scrapers import SleeperScraper
from models import SleeperWeeklyData, db
from utils import setup_logging
from routes.helpers import with_error_handling

sleeper_research_bp = Blueprint(
    'sleeper_research', __name__, url_prefix='/api/sleeper/players')
logger = setup_logging()


@sleeper_research_bp.route('/research/<string:season>', methods=['GET'])
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


@sleeper_research_bp.route('/research/<string:season>', methods=['POST', 'PUT'])
@with_error_handling
def refresh_research_data(season: str):
    """
    Refresh/Update research data
    ---
    tags:
      - Sleeper Research
    summary: Refresh/Update research data
    description: Refresh research data from Sleeper API for a specific season.
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
        'data': research_data.get('research_data', []),
        'source': 'database',
        'database_saved': True,
        'timestamp': datetime.now(UTC).isoformat()
    })
