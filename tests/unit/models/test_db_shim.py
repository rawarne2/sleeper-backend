"""The db shim must expose the Flask-SQLAlchemy surface the codebase uses."""
import threading

from sqlalchemy import func, select

from models.extensions import db, session_scope


def test_db_exposes_sqlalchemy_names():
    for name in ("Column", "Integer", "BigInteger", "String", "Text", "DateTime",
                 "Date", "Boolean", "Numeric", "Float", "ForeignKey",
                 "UniqueConstraint", "Index", "JSON", "relationship", "Model"):
        assert hasattr(db, name), f"db.{name} missing"


def test_session_roundtrip():
    from models.entities import Player
    db.configure("sqlite:///:memory:", None)
    db.create_all()
    try:
        p = Player(player_name="Test Guy", position="WR")
        db.session.add(p)
        db.session.commit()
        assert db.session.scalar(select(func.count()).select_from(Player)) == 1
        assert db.session.execute(select(Player).filter_by(position="WR")).scalars().first().player_name == "Test Guy"
    finally:
        db.drop_all()
        db.session.remove()


def test_session_scope_isolates_and_removes():
    db.configure("sqlite:///:memory:", None)
    db.create_all()
    try:
        with session_scope() as s1:
            obj_a = s1()  # hold a reference so CPython cannot reuse the address
            id_a = id(obj_a)
        with session_scope() as s2:
            obj_b = s2()
            id_b = id(obj_b)
        assert id_a != id_b
    finally:
        db.drop_all()


def test_session_remove_resets_registry():
    db.configure("sqlite:///:memory:", None)
    db.create_all()
    try:
        first = db.session()  # hold references so CPython cannot reuse the address
        db.session.remove()
        second = db.session()
        assert second is not first  # remove() drops the scoped session; a fresh one is created
    finally:
        db.drop_all()
        db.session.remove()


def test_thread_id_fallback_gives_distinct_sessions_per_thread():
    db.configure("sqlite:///:memory:", None)
    sessions = {}

    def grab(key):
        obj = db.session()  # hold a reference so CPython cannot reuse the address
        sessions[key] = (id(obj), obj)
        db.session.remove()

    t1 = threading.Thread(target=grab, args=("a",))
    t2 = threading.Thread(target=grab, args=("b",))
    t1.start(); t1.join()
    t2.start(); t2.join()
    assert sessions["a"][0] != sessions["b"][0]  # no ContextVar set => thread-id fallback scopes per thread
