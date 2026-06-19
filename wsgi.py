"""ASGI entry point for Gunicorn (Uvicorn worker) and Uvicorn.

Exposes the FastAPI ``app``: ``vercel_app`` on Vercel, ``app`` locally/Docker.
The module name is kept as ``wsgi`` so existing process managers that target
``wsgi:app`` keep working after the FastAPI migration.
"""
import os

if os.getenv('VERCEL'):
    from vercel_app import app
else:
    from app import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("wsgi:app", host="0.0.0.0", port=5001)
