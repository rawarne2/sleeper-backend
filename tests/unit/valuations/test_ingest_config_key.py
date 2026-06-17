# tests/unit/valuations/test_ingest_config_key.py
from datetime import datetime, UTC
from unittest.mock import patch
from models.entities import Player, ValueSnapshot
from models.extensions import db
from services.valuations.base import ValuationRow
from scrapers.pipelines import ingest_valuations


def test_ingest_persists_config_key(app_context):
    p = Player(player_name="Josh Allen", position="QB", team="BUF",
               match_key="joshallen-QB", sleeper_player_id="4984",
               last_updated=datetime.now(UTC))
    db.session.add(p)
    db.session.commit()

    rows = [
        ValuationRow(source_key="fantasycalc", external_id="1234", name="Josh Allen",
                     position="QB", team="BUF", metric_key="value",
                     metric_value=8000.0, rank=3, sleeper_id="4984",
                     config_key="12-2-0.5", as_of=datetime.now(UTC)),
    ]

    with patch("scrapers.pipelines.registry.get_source") as gs:
        src = gs.return_value
        src.meta.key = "fantasycalc"
        src.meta.display_name = "FantasyCalc"
        src.meta.kind = "trade_value"
        src.meta.attribution_url = "https://fantasycalc.com/"
        src.fetch.return_value = rows
        ingest_valuations(["fantasycalc"], season="2026",
                          league_format="superflex", league_settings={})

    snaps = ValueSnapshot.query.filter_by(source_key="fantasycalc").all()
    assert len(snaps) == 1
    assert snaps[0].config_key == "12-2-0.5"
