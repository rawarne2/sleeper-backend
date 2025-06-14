#!/bin/sh

# Initialize the database
echo "Initializing database..."
flask init_db

echo "Starting Flask application..."
echo "Database is ready - you can now call /api/ktc/refresh endpoints to populate data"
exec python app.py 