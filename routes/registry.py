"""Blueprint registration for the Flask app."""
from flask import Flask

import services.valuations.sources  # noqa: F401 -- registers default valuation sources
from .dashboard_league import dashboard_bp
from .players_all import players_all_bp
from .maintenance import maintenance_bp
from .sleeper.stats import sleeper_stats_bp
from .trade_analyzer import trade_analyzer_bp
from .valuations import valuations_bp


def register_blueprints(app: Flask) -> None:
    """Register all route blueprints with the Flask app."""
    app.register_blueprint(sleeper_stats_bp)
    app.register_blueprint(maintenance_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(trade_analyzer_bp)
    app.register_blueprint(valuations_bp)
    app.register_blueprint(players_all_bp)
