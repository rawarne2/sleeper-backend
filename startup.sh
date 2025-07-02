#!/bin/sh

# Wait for database to be available (optional health check)
echo "Initializing database..."
flask init_db

echo "Starting Flask application..."
echo "Database is ready - you can now call /api/ktc/refresh endpoints to populate data"
exec python app.py 