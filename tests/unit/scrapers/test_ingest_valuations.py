# tests/unit/scrapers/test_ingest_valuations.py
from datetime import datetime, UTC
from unittest.mock import patch
from models.entities import Player, ValueSnapshot, ValueSource
from models.extensions import db
from services.valuations.base import ValuationRow
from scrapers.pipelines import ingest_valuations


def _fc_rows():
    return [
        ValuationRow(source_key="fantasycalc", external_id="1234", name="Josh Allen",
                     position="QB", team="BUF", metric_key="value",
                     metric_value=8000.0, rank=3, sleeper_id="4984", as_of=datetime.now(UTC)),
        ValuationRow(source_key="fantasycalc", external_id="9001", name="2026 Pick 1.01",
                     position="PICK", team=None, metric_key="value",
                     metric_value=5000.0, rank=40, sleeper_id=None, as_of=datetime.now(UTC)),
    ]


def test_ingest_resolves_by_sleeper_id_and_skips_picks(app_context):
    p = Player(player_name="Josh Allen", position="QB", team="BUF",
               match_key="joshallen-QB", sleeper_player_id="4984",
               last_updated=datetime.now(UTC))
    db.session.add(p)
    db.session.commit()

    with patch("scrapers.pipelines.registry.get_source") as gs:
        src = gs.return_value
        src.meta.key = "fantasycalc"
        src.meta.display_name = "FantasyCalc"
        src.meta.kind = "trade_value"
        src.meta.attribution_url = "https://fantasycalc.com/"
        src.fetch.return_value = _fc_rows()
        result = ingest_valuations(["fantasycalc"], season="2026",
                                   league_format="superflex", league_settings={})

    snaps = ValueSnapshot.query.filter_by(source_key="fantasycalc").all()
    assert len(snaps) == 1                 # PICK row skipped
    assert snaps[0].player_id == p.id      # resolved by sleeper_id "4984"
    assert ValueSource.query.get("fantasycalc").last_synced_at is not None
