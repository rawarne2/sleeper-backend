from flask import Blueprint, jsonify, request
import json
from typing import Any, Dict, List, Optional, Tuple

from cache.redis_dashboard import invalidate_dashboard_league_caches_for_ktc_dimensions
from scrapers.sleeper_scraper import SleeperScraper
from models.entities import SleeperWeeklyData
from models.extensions import db
from utils.datetime_serialization import utc_now_rfc3339
from utils.helpers import setup_logging
from routes.helpers import with_error_handling

sleeper_research_bp = Blueprint(
    'sleeper_research', __name__, url_prefix='/api/sleeper/players')
logger = setup_logging()


def _parse_week_param(value: Optional[str]) -> Tuple[Optional[int], bool, Optional[str]]:
    """Parse ?week=... where 'all' means weeks 1..18."""
    raw = (value or '1').strip().lower()
    if raw == 'all':
        return None, True, None
    try:
        week = int(raw)
    except (TypeError, ValueError):
        return None, False, "week must be an integer or 'all'"
    if week < 1 or week > 18:
        return None, False, "week must be between 1 and 18, or 'all'"
    return week, False, None


def _refresh_research_for_week(season: str, week: int, league_type: str) -> Dict[str, Any]:
    """Fetch + replace a single week of research rows."""
    research_data = SleeperScraper.scrape_research_data(season, week, league_type)
    if not research_data.get('success'):
        return {
            'status': 'error',
            'week': week,
            'error': research_data.get('error', 'Unknown error'),
        }

    raw_rd = research_data.get('research_data')
    if not isinstance(raw_rd, dict):
        return {
            'status': 'error',
            'week': week,
            'error': f"Unexpected research payload shape: {type(raw_rd).__name__}",
        }

    SleeperWeeklyData.query.filter_by(
        season=season,
        week=week,
        league_type=league_type
    ).delete()

    saved_count = 0
    for player_id, player_data in raw_rd.items():
        try:
            serialized = json.dumps(player_data)
        except (TypeError, ValueError) as e:
            logger.error(
                "Error serializing research record for player %s week=%s: %s",
                player_id,
                week,
                e,
            )
            continue
        new_record = SleeperWeeklyData(
            season=season,
            week=week,
            league_type=league_type,
            player_id=player_id,
            research_data=serialized
        )
        db.session.add(new_record)
        saved_count += 1

    db.session.commit()
    return {
        'status': 'success',
        'week': week,
        'saved_count': saved_count,
        'total_players': len(raw_rd),
    }


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
        maximum: 18
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
    week, fetch_all_weeks, week_error = _parse_week_param(request.args.get('week'))
    if week_error:
        return jsonify({
            'status': 'error',
            'error': week_error,
            'season': season,
        }), 400
    league_type = request.args.get('league_type', 'dynasty')

    logger.info(
        "Research data requested for season: %s, week: %s", season, 'all' if fetch_all_weeks else week)

    # Check database first
    query = SleeperWeeklyData.query.filter_by(
        season=season,
        league_type=league_type
    )
    if fetch_all_weeks:
        query = query.filter(SleeperWeeklyData.week.between(1, 18))
    else:
        query = query.filter_by(week=week)
    research_records = query.all()

    if research_records:
        logger.info("Found %s research records in database",
                    len(research_records))
        return jsonify({
            'status': 'success',
            'data': [record.to_dict() for record in research_records],
            'week': 'all' if fetch_all_weeks else week,
            'source': 'database',
            'database_saved': True,
            'timestamp': utc_now_rfc3339(),
        })

    if fetch_all_weeks:
        return jsonify({
            'status': 'error',
            'error': 'No research data found for weeks 1-18',
            'details': 'Run PUT /api/sleeper/players/research/{season}?week=all first',
            'season': season,
        }), 404

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
        'timestamp': utc_now_rfc3339(),
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
        maximum: 18
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
    week, refresh_all_weeks, week_error = _parse_week_param(request.args.get('week'))
    if week_error:
        return jsonify({
            'status': 'error',
            'error': week_error,
            'season': season,
        }), 400
    league_type = request.args.get('league_type', 'dynasty')

    logger.info(
        "Manual refresh requested for research data: season=%s, week=%s",
        season,
        'all' if refresh_all_weeks else week,
    )

    weeks: List[int] = list(range(1, 19)) if refresh_all_weeks else [int(week)]
    per_week: List[Dict[str, Any]] = []
    total_saved = 0
    failed = 0
    first_error: Optional[str] = None

    for wk in weeks:
        res = _refresh_research_for_week(season, wk, league_type)
        per_week.append(res)
        if res.get('status') == 'success':
            total_saved += int(res.get('saved_count', 0))
        else:
            failed += 1
            if first_error is None:
                first_error = str(res.get('error', 'Unknown error'))

    invalidate_dashboard_league_caches_for_ktc_dimensions(None, None, None)

    if failed == len(weeks):
        return jsonify({
            'status': 'error',
            'error': 'Failed to refresh research data',
            'details': first_error or 'Unknown error',
            'season': season,
            'week': 'all' if refresh_all_weeks else week,
            'league_type': league_type,
        }), 400

    return jsonify({
        'status': 'success',
        'message': 'Research data refreshed successfully',
        'season': season,
        'week': 'all' if refresh_all_weeks else week,
        'league_type': league_type,
        'refresh_results': {
            'saved_count': total_saved,
            'weeks_attempted': len(weeks),
            'weeks_failed': failed,
            'weeks': per_week,
        },
        'source': 'database',
        'database_saved': True,
        'timestamp': utc_now_rfc3339(),
    })
