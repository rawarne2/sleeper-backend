from datetime import datetime, UTC
from flask import Blueprint, jsonify
from scrapers import KTCScraper
from managers import DatabaseManager
from utils import setup_logging
from scrapers import scrape_and_save_all_ktc_data
from routes.helpers import with_error_handling

ktc_bulk_bp = Blueprint('ktc_bulk', __name__, url_prefix='/api/ktc')
logger = setup_logging()


@ktc_bulk_bp.route('/refresh/all', methods=['POST'])
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
