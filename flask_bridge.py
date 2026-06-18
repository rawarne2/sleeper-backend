"""Builds the shrinking legacy Flask app from not-yet-migrated blueprints.

The FastAPI app's ASGI middleware already scopes/removes db.session per request
(the ContextVar token propagates into the WSGI threadpool), but we also register
teardown_appcontext here to match Flask-SQLAlchemy semantics for any Flask
app-context usage. Deleted once every blueprint is migrated.
"""
from flask import Flask

from models.extensions import db
from routes.registry import register_blueprints


def build_flask_bridge() -> Flask:
    flask_app = Flask(__name__)

    @flask_app.teardown_appcontext
    def _remove_session(exc=None):
        db.session.remove()

    register_blueprints(flask_app)
    return flask_app
