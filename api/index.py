from app import app, db
import sys
import os

# Add the parent directory to the Python path to import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Initialize the database tables on first import
try:
    with app.app_context():
        db.create_all()
        print("Database initialized successfully")
except Exception as e:
    print(f"Database initialization warning: {e}")

# Export the Flask app for Vercel
# Vercel will handle the WSGI interface automatically
app = app
