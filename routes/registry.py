"""Blueprint registration for the Flask app."""
from flask import Flask

import services.valuations.sources  # noqa: F401 -- registers default valuation sources
from .trade_analyzer import trade_analyzer_bp
from .valuations import valuations_bp


def register_blueprints(app: Flask) -> None:
    """Register all route blueprints with the Flask app."""
    app.register_blueprint(trade_analyzer_bp)
    app.register_blueprint(valuations_bp)
