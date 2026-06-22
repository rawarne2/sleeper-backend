# tests/api/dashboard/test_bundle_values.py
from datetime import datetime, UTC
from models.entities import Player, PlayerKTCSuperflexValues, ValueSnapshot
from models.extensions import db


def test_player_payload_includes_values_block(app_context):
    from routes.dashboard_league import _player_to_dashboard_dict
    p = Player(player_name="Josh Allen", position="QB", team="BUF",
               match_key="joshallen-QB", last_updated=datetime.now(UTC))
    db.session.add(p)
    db.session.flush()
    db.session.add(
        PlayerKTCSuperflexValues(player_id=p.id, is_redraft=False, value=8200, rank=2)
    )
    db.session.add_all([
        ValueSnapshot(player_id=p.id, source_key="ktc", league_format="superflex",
                      metric_key="value", metric_value=8200.0, rank=2, as_of=datetime.now(UTC)),
        ValueSnapshot(player_id=p.id, source_key="fantasycalc", league_format="superflex",
                      metric_key="value", metric_value=7900.0, rank=3, as_of=datetime.now(UTC)),
    ])
    db.session.commit()

    from services.valuations.latest import latest_player_values
    vmap = latest_player_values("superflex")
    out = _player_to_dashboard_dict(p, "superflex", "tep", False, values_by_player_id=vmap)
    assert "values" in out
    assert out["values"]["sources"]["ktc"]["value"] == 8200.0
    assert out["values"]["sources"]["fantasycalc"]["value"] == 7900.0
    assert out["values"]["consensus"] is not None
