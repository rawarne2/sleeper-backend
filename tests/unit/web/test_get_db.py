def test_get_db_yields_working_request_scoped_session(app_context):
    from web.db import get_db
    from models.entities import Player

    gen = get_db()
    session = next(gen)
    try:
        session.add(Player(player_name="Dep Guy", position="QB"))
        session.commit()
        assert session.query(Player).filter_by(position="QB").count() == 1
    finally:
        gen.close()


def test_get_db_shares_the_global_scoped_session(app_context):
    # During the migration the dependency must hand out the same session the
    # legacy global db.session resolves to, so mixed converted/unconverted code
    # stays in one transaction per request.
    from web.db import get_db
    from models.extensions import db

    gen = get_db()
    session = next(gen)
    try:
        assert session is db.session() or session is db.session
    finally:
        gen.close()
