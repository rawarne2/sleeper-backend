# tests/unit/valuations/test_latest_config_key.py
from datetime import datetime, UTC
from models.entities import ValueSnapshot
from models.extensions import db
from services.valuations.latest import latest_player_values


def test_latest_filters_fantasycalc_by_config_key(app_context):
    now = datetime.now(UTC)
    rows = [
        # FantasyCalc value for the same player in two configs
        ("fantasycalc", 1, "value", 7900.0, "12-2-1.0", now),
        ("fantasycalc", 1, "value", 7100.0, "12-2-0.5", now),
        # KTC value carries no config_key (NULL) and must match regardless
        ("ktc", 1, "value", 8000.0, None, now),
    ]
    for sk, pid, mk, mv, cfg, asof in rows:
        db.session.add(ValueSnapshot(player_id=pid, source_key=sk, league_format="superflex",
                                     metric_key=mk, metric_value=mv, config_key=cfg, as_of=asof))
    db.session.commit()

    out = latest_player_values("superflex", fc_config_key="12-2-0.5")
    assert out[1]["sources"]["fantasycalc"]["value"] == 7100.0  # 0.5 PPR config
    assert out[1]["sources"]["ktc"]["value"] == 8000.0          # KTC unaffected by config_key
