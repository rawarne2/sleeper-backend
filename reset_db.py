#!/usr/bin/env python
from app import app, db

def reset_db():
    with app.app_context():
        db.drop_all()
        db.create_all()
        print("Database reset and schema re-created.")

reset_db()