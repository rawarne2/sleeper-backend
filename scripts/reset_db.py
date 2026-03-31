#!/usr/bin/env python
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app import app, db

def reset_db():
    with app.app_context():
        db.drop_all()
        db.create_all()
        print("Database reset and schema re-created.")

reset_db()