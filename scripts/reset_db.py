#!/usr/bin/env python
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import app  # noqa: F401 - importing configures the db engine (db.configure)
from models.extensions import db, session_scope

def reset_db():
    with session_scope():
        db.drop_all()
        db.create_all()
        print("Database reset and schema re-created.")

reset_db()