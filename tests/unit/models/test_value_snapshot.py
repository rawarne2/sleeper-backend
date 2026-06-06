from datetime import datetime, UTC
from models.entities import ValueSnapshot, ValueSource
from models.extensions import db


def test_value_snapshot_roundtrip(app_context):
    snap = ValueSnapshot(
        player_id=1, source_key="fantasycalc", league_format="superflex",
        metric_key="value", metric_value=5800.0, rank=12,
        as_of=datetime.now(UTC),
    )
    db.session.add(snap)
    db.session.commit()
    got = ValueSnapshot.query.filter_by(source_key="fantasycalc").one()
    assert got.metric_value == 5800.0
    assert got.player_id == 1
    assert got.pick_key is None


def test_value_source_registry_row(app_context):
    src = ValueSource(source_key="ktc", display_name="KeepTradeCut", kind="trade_value")
    db.session.add(src)
    db.session.commit()
    assert ValueSource.query.get("ktc").kind == "trade_value"
