# tests/unit/valuations/test_latest.py
from datetime import datetime, UTC, timedelta
from models.entities import ValueSnapshot
from models.extensions import db
from services.valuations.latest import latest_player_values


def test_latest_player_values_blends_and_keeps_sources(app_context):
    now = datetime.now(UTC)
    rows = [
        ("ktc", 1, "value", 8000.0, now - timedelta(days=1)),
        ("ktc", 1, "value", 8200.0, now),                 # newer wins
        ("fantasycalc", 1, "value", 7900.0, now),
        ("ktc", 2, "value", 4000.0, now),
        ("fantasycalc", 2, "value", 4200.0, now),
    ]
    for sk, pid, mk, mv, asof in rows:
        db.session.add(ValueSnapshot(player_id=pid, source_key=sk, league_format="superflex",
                                     metric_key=mk, metric_value=mv, as_of=asof))
    db.session.commit()

    out = latest_player_values("superflex")
    assert out[1]["sources"]["ktc"]["value"] == 8200.0   # latest, not 8000
    assert out[1]["sources"]["fantasycalc"]["value"] == 7900.0
    assert out[1]["blended"] is not None
    assert out[1]["blended"] > out[2]["blended"]          # player 1 ranks above player 2
