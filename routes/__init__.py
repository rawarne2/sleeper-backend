"""
Routes package initialization and blueprint registration.

This module registers all the Flask blueprints for the different API endpoints.
"""
from flask import Blueprint, Flask
from .health import health_bp
from .ktc.rankings import ktc_rankings_bp
from .ktc.bulk import ktc_bulk_bp
from .sleeper.players import sleeper_players_bp
from .sleeper.leagues import sleeper_leagues_bp
from .sleeper.research import sleeper_research_bp
from .sleeper.stats import sleeper_stats_bp


api_bp = Blueprint('api', __name__, url_prefix='/api')


def register_blueprints(app: Flask) -> None:
    """
    Register all route blueprints with the Flask app.

    Args:
        app: The Flask application instance
    """
    # Health check endpoints
    app.register_blueprint(health_bp)

    # KTC endpoints
    app.register_blueprint(ktc_rankings_bp)
    app.register_blueprint(ktc_bulk_bp)

    # Sleeper endpoints
    app.register_blueprint(sleeper_players_bp)
    app.register_blueprint(sleeper_leagues_bp)
    app.register_blueprint(sleeper_research_bp)
    app.register_blueprint(sleeper_stats_bp)


# Export the main registration function
__all__ = ['api_bp', 'register_blueprints']
