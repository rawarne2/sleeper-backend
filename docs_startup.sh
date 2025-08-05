#!/bin/sh

# Set environment for local SQLite (no database server needed)
export DATABASE_URL="sqlite:///sleeper_local.db"

echo "🚀 Starting Sleeper Backend API Documentation Server..."
echo "📖 Interactive documentation will be available at: http://localhost:5000/docs/"
echo "📄 OpenAPI 3.0 specification will be available at: http://localhost:5000/openapi.json"
echo ""

# Initialize database
echo "Initializing database..."
if ! python -c "from docs_app import app, db; app.app_context().push(); db.create_all(); print('✅ Database initialized successfully')"; then
    echo "❌ Database initialization failed!"
    echo "Check the Flask application logs for details."
    exit 1
fi

echo ""
echo "🔧 Starting development server with documentation..."
echo "💡 The API is fully functional - you can test all endpoints directly from the documentation interface"
echo ""

# Start the documentation server
python docs_app.py
