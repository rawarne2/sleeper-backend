import os
from dotenv import load_dotenv
from flask import Flask, redirect, url_for
from flask_cors import CORS
from flasgger import Swagger

# Import our modules
from models import db
from routes import api_bp
from utils import DATABASE_URI, setup_logging

# Load environment variables from .env file
load_dotenv()

# Configure logging using utils function
logger = setup_logging()

# Flask App Configuration
app = Flask(__name__)

# Use environment variable or default to PostgreSQL
# Test fixtures will override this after app creation
database_uri = os.getenv('TEST_DATABASE_URI', DATABASE_URI)

# Configure engine options based on database type
engine_options = {}
if not database_uri.startswith('sqlite://'):
    # Only set PostgreSQL-specific options for non-SQLite databases
    engine_options = {
        'pool_pre_ping': True,
        'pool_recycle': 3600,
        'pool_size': 10,
        'max_overflow': 20
    }

app.config.update({
    'SQLALCHEMY_DATABASE_URI': database_uri,
    'SQLALCHEMY_TRACK_MODIFICATIONS': False,
    'SQLALCHEMY_ENGINE_OPTIONS': engine_options
})

# Initialize database with app
db.init_app(app)

# Configure CORS to allow requests from frontend
CORS(app, resources={
    r"/api/*": {
        "origins": [
            # Local development
            "http://localhost:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:3001",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            # Production frontend - specific domain
            "https://sleeper-dashboard-xi.vercel.app",
            # All Vercel deployments (regex patterns)
            r"https://sleeper-dashboard-xi.*\.vercel\.app",
            r"https://.*\.vercel\.app"
        ],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "X-Requested-With", "Accept"],
        "supports_credentials": True
    }
})

# Configure Swagger/OpenAPI documentation
swagger_config = {
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

# Swagger template configuration
swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "Sleeper Backend API",
        "description": """
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
curl "http://localhost:5000/api/ktc/rankings?league_format=superflex&is_redraft=false&tep_level=tep"

# Redraft 1QB Standard
curl "http://localhost:5000/api/ktc/rankings?league_format=1qb&is_redraft=true"
```

### League Management
```bash
# Get league data
curl "http://localhost:5000/api/sleeper/league/1210364682523656192"

# Refresh league data
curl -X POST "http://localhost:5000/api/sleeper/league/1210364682523656192/refresh"
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
    "host": "localhost:5000",
    "basePath": "",
    "schemes": ["http", "https"],
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

# Initialize Swagger
swagger = Swagger(app, config=swagger_config, template=swagger_template)

# Register blueprints
app.register_blueprint(api_bp)

# Add route for root path to redirect to docs
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
    import yaml
    import json
    
    try:
        with open('openapi.yaml', 'r') as f:
            openapi_spec = yaml.safe_load(f)
        return json.dumps(openapi_spec, indent=2), 200, {'Content-Type': 'application/json'}
    except Exception as e:
        logger.error("Error loading OpenAPI spec: %s", e)
        return {"error": "Failed to load OpenAPI specification"}, 500


@app.cli.command("init_db")
def init_db():
    """Initialize the database tables."""
    db.create_all()
    logger.info("Initialized the database.")


@app.cli.command("create_tables")
def create_tables():
    """Create all database tables including new Sleeper models."""
    with app.app_context():
        db.create_all()
        logger.info("Created all database tables successfully.")

        # Print table info
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        logger.info("Available tables: %s", tables)


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
