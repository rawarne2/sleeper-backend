"""
Simple Gunicorn configuration for production deployment
"""
import multiprocessing
import os

# Server socket
bind = "0.0.0.0:5001"

# Worker processes
workers = int(os.getenv('GUNICORN_WORKERS', str(multiprocessing.cpu_count() * 2 + 1)))
timeout = int(os.getenv('GUNICORN_TIMEOUT', '9999'))
graceful_timeout = int(os.getenv('GUNICORN_GRACEFUL_TIMEOUT', str(timeout)))

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Process naming
proc_name = "sleeper-backend"
