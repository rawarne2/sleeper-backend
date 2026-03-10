"""
Main routes module - now refactored into modular blueprint structure.

This file now serves as a simple entry point that imports and registers
all the individual route blueprints from the routes/ package.

All route logic has been moved to the appropriate modules:
- routes/health.py - Health check endpoints
- routes/ktc/rankings.py - KTC ranking endpoints
- routes/ktc/bulk.py - KTC bulk operations
- routes/sleeper/players.py - Sleeper player endpoints
- routes/sleeper/leagues.py - Sleeper league endpoints
- routes/sleeper/research.py - Sleeper research endpoints
- routes/sleeper/stats.py - Sleeper weekly stats endpoints
- routes/helpers.py - Shared helper functions
"""

from flask import Blueprint
from routes import register_blueprints

# Create a main API blueprint (optional - for backwards compatibility)
api_bp = Blueprint('api', __name__, url_prefix='/api')

# Note: Individual blueprints are now registered directly with the app
# via the register_blueprints function in routes/__init__.py

# This file is kept minimal to maintain the existing structure
# while the actual route logic has been moved to modular files
