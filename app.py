import os
from dotenv import load_dotenv
from flask import Flask

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

# Register blueprints
app.register_blueprint(api_bp)


@app.cli.command("init_db")
def init_db():
    """Initialize the database tables."""
    db.create_all()
    logger.info("Initialized the database.")


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
