"""
Shared Swagger/OpenAPI configuration for both app.py and vercel_app.py
"""
import os
import yaml
import json
from flask import redirect, url_for
from flasgger import Swagger


def get_swagger_config():
    """Get the base Swagger configuration."""
    return {
        "headers": [],
        "specs": [
            {
                "endpoint": 'apispec',
                "route": '/apispec.json',
                "rule_filter": lambda rule: True,
                "model_filter": lambda tag: True,
            }
        ],
        "static_url_path": "/flasgger_static",
        "swagger_ui": True,
        "specs_route": "/docs/",
        "title": "Sleeper Backend API Documentation",
        "version": "1.0.0",
        "description": "Interactive API documentation for the Sleeper Backend API",
        "termsOfService": "",
        "contact": {
            "name": "API Support",
            "url": "https://github.com/rawarne2/sleeper-backend"
        },
        "license": {
            "name": "MIT",
            "url": "https://opensource.org/licenses/MIT"
        }
    }


def get_swagger_template(host="localhost:5000", schemes=None):
    """
    Get the Swagger template configuration.

    Args:
        host: The host for the API (default: localhost:5000 for dev)
        schemes: List of schemes (default: ["http", "https"] for dev, ["https"] for prod)
    """
    if schemes is None:
        schemes = ["http", "https"] if "localhost" in host else ["https"]

    # Determine if this is production based on host
    is_production = "vercel.app" in host

    # Use production URLs in examples if in production
    base_url = f"https://{host}" if is_production else f"http://{host}"

    return {
        "swagger": "2.0",
        "info": {
            "title": "Sleeper Backend API",
            "description": f"""
A comprehensive fantasy football API that aggregates data from **KeepTradeCut (KTC)** and **Sleeper API**.

This API provides comprehensive fantasy football data by combining:
- 🏈 **KeepTradeCut (KTC)**: Player rankings and trade values (Dynasty & Redraft rankings, 1QB & Superflex league formats, TEP scoring variations)
- 🏈 **Sleeper API**: Player data & league management (Comprehensive player profiles, League management, Research data and projections)

## Performance Optimizations
- **Database Caching Strategy**: First API call fetches from external APIs and caches in database, subsequent calls served instantly from local cache
- **Response Time Guidelines**: First refresh call takes 30-60 seconds, cached data retrieval < 1 second, health checks < 100ms
- **Gunicorn Multi-Worker Setup**: 9 worker processes for concurrent request handling with load balancing

## Getting Started
1. Check system health: `GET /api/ktc/health`
2. Load initial data: `POST /api/ktc/refresh?league_format=superflex`
3. Get player rankings: `GET /api/ktc/rankings?league_format=superflex`

## API Usage Examples

### KTC Rankings
```bash
# Dynasty Superflex with TEP
curl "{base_url}/api/ktc/rankings?league_format=superflex&is_redraft=false&tep_level=tep"

# Redraft 1QB Standard
curl "{base_url}/api/ktc/rankings?league_format=1qb&is_redraft=true"
```

### League Management
```bash
# Get league data
curl "{base_url}/api/sleeper/league/1210364682523656192"

# Refresh league data
curl -X POST "{base_url}/api/sleeper/league/1210364682523656192/refresh"
```
            """,
            "version": "1.0.0",
            "contact": {
                "name": "API Support",
                "url": "https://github.com/rawarne2/sleeper-backend"
            },
            "license": {
                "name": "MIT",
                "url": "https://opensource.org/licenses/MIT"
            }
        },
        "host": host,
        "basePath": "",
        "schemes": schemes,
        "consumes": ["application/json"],
        "produces": ["application/json"],
        "tags": [
            {
                "name": "Health",
                "description": "System health and status endpoints"
            },
            {
                "name": "KTC Player Rankings",
                "description": "KeepTradeCut player rankings and values"
            },
            {
                "name": "Sleeper Players",
                "description": "Sleeper player data management"
            },
            {
                "name": "Sleeper Leagues",
                "description": "Sleeper league management endpoints"
            },
            {
                "name": "Sleeper Research",
                "description": "Sleeper player research and analytics data"
            },
            {
                "name": "Bulk Operations",
                "description": "Bulk refresh operations for scheduled tasks"
            }
        ]
    }


def setup_swagger(app, host="localhost:5000", schemes=None):
    """
    Set up Swagger/OpenAPI documentation for a Flask app.

    Args:
        app: Flask application instance
        host: The host for the API (default: localhost:5000 for dev)
        schemes: List of schemes (default: ["http", "https"] for dev, ["https"] for prod)
    """
    swagger_config = get_swagger_config()
    swagger_template = get_swagger_template(host, schemes)

    # Initialize Swagger
    swagger = Swagger(app, config=swagger_config, template=swagger_template)

    return swagger


def add_documentation_routes(app, logger):
    """
    Add documentation routes to a Flask app.

    Args:
        app: Flask application instance
        logger: Logger instance for error handling
    """
    @app.route('/')
    def index():
        """
        Root endpoint - redirects to API documentation
        ---
        responses:
          302:
            description: Redirect to API documentation
        """
        return redirect(url_for('flasgger.apidocs'))

    @app.route('/openapi.json')
    def openapi_spec():
        """
        OpenAPI 3.0 specification endpoint
        ---
        responses:
          200:
            description: OpenAPI 3.0 specification
            content:
              application/json:
                schema:
                  type: object
        """
        try:
            with open('openapi.yaml', 'r', encoding='utf-8') as f:
                openapi_data = yaml.safe_load(f)
            return json.dumps(openapi_data, indent=2), 200, {'Content-Type': 'application/json'}
        except (FileNotFoundError, yaml.YAMLError, TypeError, ValueError) as e:
            logger.error("Error loading OpenAPI spec: %s", e)
            return {"error": "Failed to load OpenAPI specification"}, 500
