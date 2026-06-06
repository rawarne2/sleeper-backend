# tests/unit/valuations/test_ktc_source.py
from datetime import datetime, UTC
from models.entities import Player, PlayerKTCSuperflexValues
from models.extensions import db
from services.valuations.sources.ktc import KtcSource


def test_ktc_source_emits_value_rows_from_db(app_context):
    p = Player(player_name="Josh Allen", position="QB", team="BUF",
               match_key="joshallen-QB", last_updated=datetime.now(UTC))
    db.session.add(p)
    db.session.flush()
    db.session.add(PlayerKTCSuperflexValues(player_id=p.id, is_redraft=False, value=8200, rank=2))
    db.session.commit()

    rows = KtcSource().fetch(season="2026", league_format="superflex", league_settings={})
    val = [r for r in rows if r.external_id == str(p.id) and r.metric_key == "value"]
    assert val and val[0].metric_value == 8200
