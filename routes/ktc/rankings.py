from flask import Blueprint, current_app, jsonify, make_response, request
from managers.database_manager import DatabaseManager
from routes.helpers import filter_players_by_format
from utils.datetime_serialization import format_instant_rfc3339_utc, utc_now_rfc3339
from utils.helpers import validate_parameters, setup_logging
from routes.ktc.rankings_cache import (
    get_cached_rankings_json,
    invalidate_rankings_cache,
    set_cached_rankings_json,
)
from services.ktc_refresh_async import (
    execute_ktc_refresh_pipeline,
    get_refresh_job,
    try_begin_async_job,
)

ktc_rankings_bp = Blueprint('ktc_rankings', __name__, url_prefix='/api/ktc')
logger = setup_logging()

_SYNC_QUERY_TRUE = frozenset({'1', 'true', 'yes'})
_SYNC_QUERY_FALSE = frozenset({'0', 'false', 'no'})


def _wants_synchronous_refresh() -> bool:
    """Blocking pipeline (multi-minute). Use sync=1 for tests or operators."""
    sync_raw = (request.args.get('sync') or '').strip().lower()
    if sync_raw in _SYNC_QUERY_TRUE:
        return True
    if sync_raw in _SYNC_QUERY_FALSE:
        return False
    async_raw = (request.args.get('async') or '').strip().lower()
    if async_raw in _SYNC_QUERY_FALSE:
        return True
    if async_raw in _SYNC_QUERY_TRUE:
        return False
    return False


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

      By default the handler **returns immediately** (HTTP 202) after validation and enqueues
      scrape + DB save + cache invalidation in a background thread. Poll
      ``GET /api/ktc/refresh/status/<job_id>`` or refetch ``GET /api/dashboard/league/<id>`` until
      ``ktcLastUpdated`` advances.

      **sync=1** (or ``sync=true``): run the full pipeline in the request (can exceed one minute).
      Use for scripts, tests, or environments where background work after the response is unreliable.

      KTC provides a full rankings page per dynasty/redraft mode; there is no API to refresh only
      roster player IDs—optional ``league_id`` / ``season`` scoping is not supported.

      **Synchronous UX contract**: Anything beyond parameter validation and a quick DB ping should
      stay off the default code path; full scrape + DB write is async unless ``sync=1``.
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
      - name: sync
        in: query
        description: |
          If true (1/yes/true), run scrape + DB save synchronously and return 200 with full payload.
          Default is async (202).
        required: false
        type: string
        enum: ['0', '1', 'true', 'false', 'yes', 'no']
        default: 'false'
      - name: async
        in: query
        description: If false, same as sync=1 (blocking refresh).
        required: false
        type: string
        enum: ['0', '1', 'true', 'false', 'yes', 'no']
    responses:
      202:
        description: Refresh accepted; running in background
        schema:
          type: object
          properties:
            accepted:
              type: boolean
              example: true
            status:
              type: string
              example: queued
            job_id:
              type: string
              format: uuid
            poll_url:
              type: string
            already_running:
              type: boolean
            message:
              type: string
            hint:
              type: string
      200:
        description: Rankings refreshed successfully (sync=1 only)
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
        is_redraft_str = request.args.get('is_redraft', 'false')
        league_format_str = request.args.get('league_format', '1qb')
        tep_level_str = request.args.get('tep_level', '')

        valid, league_format, tep_level, error_msg = validate_parameters(
            is_redraft_str, league_format_str, tep_level_str)
        if not valid:
            return jsonify({'error': error_msg}), 400

        is_redraft = is_redraft_str.lower() == 'true'

        if _wants_synchronous_refresh():
            logger.info("KTC refresh (sync=1): full pipeline in request thread")
            outcome = execute_ktc_refresh_pipeline(
                league_format, is_redraft, tep_level)
            return jsonify(outcome.body), outcome.status_code

        logger.info(
            "KTC refresh: enqueue background job (use sync=1 for blocking)")
        if not DatabaseManager.verify_database_connection():
            logger.error(
                "Database connection verification failed before refresh enqueue")
            return jsonify({
                'error': 'Database connection failed',
                'details': 'Cannot establish database connection before starting refresh operation'
            }), 500

        app = current_app._get_current_object()
        job_id, already_running = try_begin_async_job(
            app, league_format, is_redraft, tep_level)

        return jsonify({
            'accepted': True,
            'status': 'queued',
            'job_id': job_id,
            'already_running': already_running,
            'message': (
                'KTC refresh accepted; running in background'
                + (' (already in progress for this configuration)'
                   if already_running else '')
            ),
            'poll_url': f'/api/ktc/refresh/status/{job_id}',
            'is_redraft': is_redraft,
            'league_format': league_format,
            'tep_level': tep_level or '',
            'hint': 'Refetch GET /api/dashboard/league/<id> until ktcLastUpdated advances.',
        }), 202

    except Exception as e:
        logger.error("Error refreshing rankings: %s", e)
        return jsonify({
            'error': 'Internal server error during refresh',
            'details': str(e),
            'database_success': False,
            'context': 'Error occurred in main refresh flow'
        }), 500


@ktc_rankings_bp.route('/refresh/status/<job_id>', methods=['GET'])
def refresh_rankings_job_status(job_id: str):
    """Poll KTC background refresh job status."""
    rec = get_refresh_job(job_id)
    if not rec:
        return jsonify({
            'error': 'Unknown job_id',
            'job_id': job_id,
        }), 404
    return jsonify({
        'job_id': rec['job_id'],
        'status': rec['status'],
        'created_at': rec['created_at'],
        'finished_at': rec['finished_at'],
        'league_format': rec['league_format'],
        'is_redraft': rec['is_redraft'],
        'tep_level': rec['tep_level'],
        'error': rec['error'],
        'summary': rec['summary'],
    })


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

        invalidate_rankings_cache()
        return jsonify({
            'message': 'Database cleanup completed',
            'timestamp': utc_now_rfc3339(),
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

        cached = get_cached_rankings_json(is_redraft, league_format, tep_level)
        if cached is not None:
            resp = make_response(cached)
            resp.mimetype = 'application/json'
            resp.headers['Cache-Control'] = (
                'public, max-age=3600, stale-while-revalidate=86400'
            )
            resp.headers['X-Rankings-Cache'] = 'HIT'
            return resp

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

        players_data = filter_players_by_format(
            players, league_format, tep_level)

        payload = {
            'timestamp': format_instant_rfc3339_utc(last_updated),
            'is_redraft': is_redraft,
            'league_format': league_format,
            'tep_level': tep_level,
            'count': len(players_data),
            'players': players_data
        }
        json_bytes = set_cached_rankings_json(
            is_redraft, league_format, tep_level, payload
        )
        resp = make_response(json_bytes)
        resp.mimetype = 'application/json'
        resp.headers['Cache-Control'] = (
            'public, max-age=3600, stale-while-revalidate=86400'
        )
        resp.headers['X-Rankings-Cache'] = 'MISS'
        return resp

    except Exception as e:
        logger.error("Error retrieving rankings: %s", e)
        return jsonify({
            'error': 'Internal server error during rankings retrieval',
            'details': str(e)
        }), 500
