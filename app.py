import os
from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS

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
            # Production frontend
            "https://sleeper-dashboard-xi.vercel.app",
        ],
        "origin_regex": [
            r"https://sleeper-dashboard-xi.*\.vercel\.app",  # All Vercel deployments
            # Backup: allow all Vercel apps (can remove later)
            r"https://.*\.vercel\.app"
        ],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "X-Requested-With", "Accept"],
        "supports_credentials": True
    }
})

# Register blueprints
app.register_blueprint(api_bp)


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
