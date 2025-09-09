"""
WSGI entry point for Gunicorn
"""
import os

# Use vercel_app for Vercel deployment, app.py for local/Docker
if os.getenv('VERCEL'):
    from vercel_app import app
else:
    from app import app

if __name__ == "__main__":
    app.run()
