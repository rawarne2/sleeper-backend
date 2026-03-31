from datetime import datetime, UTC
from flask import Blueprint, jsonify
from managers.database_manager import DatabaseManager
from utils.helpers import setup_logging

health_bp = Blueprint('health', __name__, url_prefix='/api')
logger = setup_logging()


@health_bp.route('/ktc/health', methods=['GET'])
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
