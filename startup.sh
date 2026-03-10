#!/bin/sh

# Set default environment for local development if not already set.
# If DATABASE_URL is provided (local Postgres, Supabase, etc.), use it as-is
# and let the connection string control SSL behavior.
if [ -z "$DATABASE_URL" ]; then
    export DATABASE_URL="sqlite:///sleeper_local.db"
    echo "Using default SQLite database for local development"
else
    database_url_preview=$(printf '%s' "$DATABASE_URL" | cut -c1-80)
    echo "Using provided DATABASE_URL: ${database_url_preview}..."
fi

# Initialize database
echo "Initializing database..."
if ! python -c "
import os
import sys
from app import app, initialize_database

if not initialize_database():
    sys.exit(1)
"; then
    echo "❌ Database initialization failed!"
    echo "Check the Flask application logs for details."
    exit 1
fi

# Determine database type for display
if echo "$DATABASE_URL" | grep -q "sqlite"; then
    echo "✅ Database initialized successfully (SQLite)"
else
    echo "✅ Database initialized successfully (PostgreSQL)"
fi
echo "🚀 Starting Flask application with Gunicorn..."
echo "📖 Interactive API documentation available at: http://localhost:5001/docs/"
echo "📄 OpenAPI 3.0 specification available at: http://localhost:5001/openapi.json"
echo "🏠 Root URL redirects to documentation: http://localhost:5001/"
echo ""
echo "Database is ready - you can now call /api/ktc/refresh endpoints to populate data"

# When REMOTE_DEBUG=1, run with debugpy so VS Code can attach and breakpoints work
if [ -n "$REMOTE_DEBUG" ] && [ "$REMOTE_DEBUG" != "0" ]; then
    echo "🐛 Remote debug enabled - attach on port 5678 (e.g. VS Code 'Python: Remote Debug Docker')"
    exec python -m debugpy --listen 0.0.0.0:5678 -m gunicorn --config gunicorn.conf.py --workers 1 wsgi:app
fi

exec gunicorn --config gunicorn.conf.py wsgi:app
