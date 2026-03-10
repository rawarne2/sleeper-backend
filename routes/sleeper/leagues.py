from datetime import datetime, UTC
from flask import Blueprint, jsonify
from scrapers import SleeperScraper
from managers import DatabaseManager
from utils import setup_logging
from routes.helpers import with_error_handling

sleeper_leagues_bp = Blueprint(
    'sleeper_leagues', __name__, url_prefix='/api/sleeper/league')
logger = setup_logging()


@sleeper_leagues_bp.route('/<string:league_id>', methods=['GET'])
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


@sleeper_leagues_bp.route('/<string:league_id>/rosters', methods=['GET'])
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


@sleeper_leagues_bp.route('/<string:league_id>/users', methods=['GET'])
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


@sleeper_leagues_bp.route('/<string:league_id>', methods=['POST', 'PUT'])
@with_error_handling
def refresh_league_data(league_id: str):
    """
    Refresh/Update league data
    ---
    tags:
      - Sleeper Leagues
    summary: Refresh/Update league data
    description: Refresh all league data from Sleeper API (league info, rosters, users).
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

    # Include the league data we just refreshed
    if results['league_data'] and results.get('league_data').get('status') == 'success':
        results['data'] = results.get('league_data').get('save_result')
        results['source'] = 'database'
    else:
        results['data'] = None
        results['source'] = 'sleeper_api'

    return jsonify(results)
