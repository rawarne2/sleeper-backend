"""Blueprint registration for the Flask app."""
from flask import Flask

from .dashboard_league import dashboard_bp
from .health import health_bp
from .ktc.bulk import ktc_bulk_bp
from .ktc.rankings import ktc_rankings_bp
from .maintenance import maintenance_bp
from .sleeper.leagues import sleeper_leagues_bp
from .sleeper.players import sleeper_players_bp
from .sleeper.research import sleeper_research_bp
from .sleeper.stats import sleeper_stats_bp


def register_blueprints(app: Flask) -> None:
    """Register all route blueprints with the Flask app."""
    app.register_blueprint(health_bp)
    app.register_blueprint(ktc_rankings_bp)
    app.register_blueprint(ktc_bulk_bp)
    app.register_blueprint(sleeper_players_bp)
    app.register_blueprint(sleeper_leagues_bp)
    app.register_blueprint(sleeper_research_bp)
    app.register_blueprint(sleeper_stats_bp)
    app.register_blueprint(maintenance_bp)
    app.register_blueprint(dashboard_bp)
