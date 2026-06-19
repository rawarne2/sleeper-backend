"""OpenAPI metadata for the FastAPI app (replaces flasgger template + openapi.yaml)."""

OPENAPI_TITLE = "Sleeper Backend API"
OPENAPI_VERSION = "1.0.0"
OPENAPI_DESCRIPTION = (
    "A comprehensive fantasy football API aggregating KeepTradeCut (KTC) and "
    "Sleeper data: player rankings & trade values (Dynasty/Redraft, 1QB/Superflex, "
    "TEP variations), league management, research/projections, a dashboard bundle, "
    "and an AI trade analyzer."
)
OPENAPI_TAGS = [
    {"name": "Health", "description": "System health and status endpoints"},
    {"name": "KTC Player Rankings", "description": "KeepTradeCut player rankings and values"},
    {"name": "Bulk Operations", "description": "Bulk refresh operations for scheduled tasks"},
    {"name": "Sleeper Players", "description": "Sleeper player data management"},
    {"name": "Sleeper Leagues", "description": "Sleeper league management endpoints"},
    {"name": "Sleeper Research", "description": "Sleeper player research and analytics data"},
    {"name": "Sleeper Weekly Stats", "description": "Sleeper weekly fantasy stats and rosters"},
    {"name": "Dashboard", "description": "Aggregated dashboard payload endpoints"},
    {"name": "Maintenance", "description": "Operator-only maintenance and cron endpoints"},
    {"name": "Trade Analyzer", "description": "AI-powered trade analysis endpoints"},
]
