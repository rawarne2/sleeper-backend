#!/bin/sh

# Set default environment for local development if not already set
if [ -z "$DATABASE_URL" ]; then
    export DATABASE_URL="sqlite:///sleeper_local.db"
    echo "Using default SQLite database for local development"
else
    echo "Using provided DATABASE_URL: ${DATABASE_URL:0:50}..."
    if echo "$DATABASE_URL" | grep -q "postgresql"; then
        echo "PostgreSQL database detected - ensuring SSL mode is disabled for local Docker"
        # Ensure sslmode=disable is set for local PostgreSQL
        if ! echo "$DATABASE_URL" | grep -q "sslmode="; then
            export DATABASE_URL="${DATABASE_URL}?sslmode=disable"
            echo "Added sslmode=disable to PostgreSQL connection string"
        fi
    fi
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
echo "📖 Interactive API documentation available at: http://localhost:5000/docs/"
echo "📄 OpenAPI 3.0 specification available at: http://localhost:5000/openapi.json"
echo "🏠 Root URL redirects to documentation: http://localhost:5000/"
echo ""
echo "Database is ready - you can now call /api/ktc/refresh endpoints to populate data"
exec gunicorn --config gunicorn.conf.py wsgi:app
