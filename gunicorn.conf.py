"""
Simple Gunicorn configuration for production deployment
"""
import multiprocessing

# Server socket
bind = "0.0.0.0:5000"

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
timeout = 30

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Process naming
proc_name = "sleeper-backend"
