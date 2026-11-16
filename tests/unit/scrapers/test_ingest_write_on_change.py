from datetime import datetime, timedelta, UTC
from unittest.mock import patch

from sqlalchemy import func, select

from models.entities import Player, ValueSnapshot
from models.extensions import db
from scrapers.pipelines import ingest_valuations
from services.valuations.base import ValuationRow


def _rows(value, trade_freq, as_of, cfg="12-2-0.5"):
    common = dict(source_key="fantasycalc", external_id="1234", name="Josh Allen",
                  position="QB", team="BUF", sleeper_id="4984", config_key=cfg, as_of=as_of)
    return [
        ValuationRow(metric_key="value", metric_value=value, rank=3, **common),
        ValuationRow(metric_key="trade_frequency", metric_value=trade_freq, rank=None, **common),
    ]


def _ingest(rows):
    with patch("scrapers.pipelines.registry.get_source") as gs:
        src = gs.return_value
        src.meta.key = "fantasycalc"
        src.meta.display_name = "FantasyCalc"
        src.meta.kind = "trade_value"
        src.meta.attribution_url = "https://fantasycalc.com/"
        src.fetch.return_value = rows
        return ingest_valuations(["fantasycalc"], season="2026",
                                 league_format="superflex", league_settings={})


def _count(**filters):
    return db.session.scalar(
        select(func.count()).select_from(ValueSnapshot).filter_by(**filters))


def _player():
    p = Player(player_name="Josh Allen", position="QB", team="BUF", match_key="joshallen-QB",
               sleeper_player_id="4984", last_updated=datetime.now(UTC))
    db.session.add(p)
    db.session.commit()
    return p


def test_identical_payload_writes_nothing(app_context):
    _player()
    t0 = datetime(2026, 11, 15, 14, 0)
    first = _ingest(_rows(8000.0, 0.4, t0))
    second = _ingest(_rows(8000.0, 0.4, t0 + timedelta(hours=1)))

    assert first["fantasycalc"].startswith("2 snapshots")
    assert second["fantasycalc"] == "0 snapshots, 0 updated, 2 unchanged"
    assert _count() == 2


def test_changed_full_metric_appends_one_row(app_context):
    _player()
    t0 = datetime(2026, 11, 15, 14, 0)
    _ingest(_rows(8000.0, 0.4, t0))
    result = _ingest(_rows(8100.0, 0.4, t0 + timedelta(days=1)))

    assert result["fantasycalc"] == "1 snapshots, 0 updated, 1 unchanged"
    assert _count(metric_key="value") == 2


def test_changed_latest_only_metric_updates_in_place(app_context):
    p = _player()
    t0 = datetime(2026, 11, 15, 14, 0)
    _ingest(_rows(8000.0, 0.4, t0))
    t1 = t0 + timedelta(days=1)
    result = _ingest(_rows(8000.0, 0.7, t1))

    assert result["fantasycalc"] == "0 snapshots, 1 updated, 1 unchanged"
    rows = db.session.execute(select(ValueSnapshot).filter_by(
        player_id=p.id, metric_key="trade_frequency")).scalars().all()
    assert len(rows) == 1
    assert rows[0].metric_value == 0.7
    assert rows[0].as_of.replace(tzinfo=None) == t1


def test_other_config_is_a_separate_key(app_context):
    _player()
    t0 = datetime(2026, 11, 15, 14, 0)
    _ingest(_rows(8000.0, 0.4, t0))
    result = _ingest(_rows(8000.0, 0.4, t0 + timedelta(hours=1), cfg="12-2-1.0"))

    assert result["fantasycalc"].startswith("2 snapshots")
    assert _count(config_key="12-2-1.0") == 2
