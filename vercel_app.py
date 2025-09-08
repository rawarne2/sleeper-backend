"""
Vercel-compatible Flask application with Supabase integration
"""
import os
from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

# Import our modules
from models import db
from utils import setup_logging

# Import routes after db is available to avoid circular imports
from routes import api_bp

# Load environment variables
load_dotenv()

# Configure logging
logger = setup_logging()

# Flask App Configuration
app = Flask(__name__)

# Supabase/Vercel database configuration
# Vercel + Supabase typically provides these environment variables
database_uri = (
    # Vercel + Supabase pooled connection (preferred)
    os.getenv('POSTGRES_URL') or
    os.getenv('POSTGRES_PRISMA_URL') or  # Alternative pooled connection
    os.getenv('DATABASE_URL') or  # Generic database URL
    os.getenv('POSTGRES_URL_NON_POOLING') or  # Non-pooled (fallback)
    # Local development fallback
    os.getenv('TEST_DATABASE_URI', 'sqlite:///sleeper_local.db')
)

# Fix URL scheme for SQLAlchemy compatibility
if database_uri and database_uri.startswith('postgres://'):
    database_uri = database_uri.replace('postgres://', 'postgresql://', 1)

# Clean up Supabase-specific connection parameters that psycopg2 doesn't recognize
if database_uri and database_uri.startswith('postgresql://'):
    try:
        parsed = urlparse(database_uri)
        query_params = parse_qs(parsed.query)

        # Remove Supabase-specific parameters that cause issues
        allowed_params = {
            'sslmode', 'connect_timeout', 'application_name',
            'sslcert', 'sslkey', 'sslrootcert', 'sslcrl'
        }

        cleaned_params = {k: v for k,
                          v in query_params.items() if k in allowed_params}

        # Rebuild the URL with cleaned parameters
        cleaned_query = urlencode(cleaned_params, doseq=True)
        cleaned_parsed = parsed._replace(query=cleaned_query)
        database_uri = urlunparse(cleaned_parsed)

        logger.info(f"Cleaned database URI parameters")
    except Exception as e:
        logger.warning(f"Failed to clean database URI: {e}")

logger.info(f"Using database connection: {database_uri[:50]}...")

# Configure engine options for Supabase/PostgreSQL
engine_options = {}
if not database_uri.startswith('sqlite://'):
    # Supabase-optimized connection settings
    engine_options = {
        'pool_pre_ping': True,
        'pool_recycle': 300,  # 5 minutes (shorter for serverless)
        'pool_size': 5,       # Smaller pool for serverless
        'max_overflow': 10,   # Reduced overflow
        'pool_timeout': 30,   # Connection timeout
        'connect_args': {
            'sslmode': 'require',  # Supabase requires SSL
            'connect_timeout': 10,
        }
    }

app.config.update({
    'SQLALCHEMY_DATABASE_URI': database_uri,
    'SQLALCHEMY_TRACK_MODIFICATIONS': False,
    'SQLALCHEMY_ENGINE_OPTIONS': engine_options
})

# Initialize database with app
db.init_app(app)

# Configure CORS to allow requests from frontend
CORS(app,
     origins=[
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
     allow_headers=["Content-Type", "Authorization",
                    "X-Requested-With", "Accept", "Origin"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
     supports_credentials=True,
     expose_headers=["Content-Range", "X-Content-Range"]
     )

# Register blueprints
app.register_blueprint(api_bp)

# Add explicit OPTIONS handler for preflight requests


@app.before_request
def handle_preflight():
    from flask import request
    if request.method == "OPTIONS":
        from flask import make_response
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin",
                             "https://sleeper-dashboard-xi.vercel.app")
        response.headers.add('Access-Control-Allow-Headers',
                             "Content-Type,Authorization,X-Requested-With,Accept,Origin")
        response.headers.add('Access-Control-Allow-Methods',
                             "GET,PUT,POST,DELETE,OPTIONS")
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response


@app.after_request
def after_request(response):
    from flask import request
    origin = request.headers.get('Origin')
    allowed_origins = [
        "https://sleeper-dashboard-xi.vercel.app",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ]

    if origin in allowed_origins:
        response.headers.add('Access-Control-Allow-Origin', origin)
        response.headers.add('Access-Control-Allow-Headers',
                             "Content-Type,Authorization,X-Requested-With,Accept,Origin")
        response.headers.add('Access-Control-Allow-Methods',
                             "GET,PUT,POST,DELETE,OPTIONS")
        response.headers.add('Access-Control-Allow-Credentials', 'true')

    return response


# Initialize database tables on startup
with app.app_context():
    try:
        db.create_all()
        logger.info("Database tables initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        # Don't fail completely - let the app start but log the error
        logger.error(
            "Application will continue but database operations may fail")

# Vercel serverless function handler
app = app
