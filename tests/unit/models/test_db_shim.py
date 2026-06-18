"""The db shim must expose the Flask-SQLAlchemy surface the codebase uses."""
import threading

from models.extensions import db, session_scope


def test_db_exposes_sqlalchemy_names():
    for name in ("Column", "Integer", "BigInteger", "String", "Text", "DateTime",
                 "Date", "Boolean", "Numeric", "Float", "ForeignKey",
                 "UniqueConstraint", "Index", "JSON", "relationship", "Model"):
        assert hasattr(db, name), f"db.{name} missing"


def test_model_query_and_session_roundtrip():
    from models.entities import Player
    db.configure("sqlite:///:memory:", None)
    db.create_all()
    try:
        p = Player(player_name="Test Guy", position="WR")
        db.session.add(p)
        db.session.commit()
        assert Player.query.count() == 1
        assert Player.query.filter_by(position="WR").first().player_name == "Test Guy"
    finally:
        db.drop_all()
        db.session.remove()


def test_session_scope_isolates_and_removes():
    db.configure("sqlite:///:memory:", None)
    db.create_all()
    seen = {}
    try:
        with session_scope() as s1:
            seen["a"] = id(s1())
        with session_scope() as s2:
            seen["b"] = id(s2())
        assert seen["a"] != seen["b"]
    finally:
        db.drop_all()
