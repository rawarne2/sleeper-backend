#!/bin/sh

# Set environment for local SQLite (no database server needed)
export DATABASE_URL="sqlite:///sleeper_local.db"

# Initialize database
echo "Initializing database..."
if ! flask init_db; then
    echo "❌ Database initialization failed!"
    echo "Check the Flask application logs for details."
    exit 1
fi

echo "✅ Database initialized successfully (SQLite)"
echo "🚀 Starting Flask application with Gunicorn..."
echo "📖 Interactive API documentation available at: http://localhost:5000/docs/"
echo "📄 OpenAPI 3.0 specification available at: http://localhost:5000/openapi.json"
echo "🏠 Root URL redirects to documentation: http://localhost:5000/"
echo ""
echo "Database is ready - you can now call /api/ktc/refresh endpoints to populate data"
exec gunicorn --config gunicorn.conf.py wsgi:app
