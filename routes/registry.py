"""Blueprint registration for the Flask app."""
from flask import Flask

import services.valuations.sources  # noqa: F401 -- registers default valuation sources


def register_blueprints(app: Flask) -> None:
    """Register all route blueprints with the Flask app."""
    return None
