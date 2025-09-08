"""
WSGI entry point for Gunicorn
"""
from vercel_app import app

if __name__ == "__main__":
    app.run()
