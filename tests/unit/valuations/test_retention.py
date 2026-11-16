from datetime import datetime, timedelta

from sqlalchemy import func, select

from models.entities import ValueSnapshot
from models.extensions import db
from services.valuations.latest import latest_player_values
from services.valuations.retention import metric_policy, prune_value_snapshots

NOW = datetime(2026, 11, 16, 12, 0, 0)


def _add(pid, metric, value, as_of, source="fantasycalc", cfg="12-2-0.5", fmt="superflex"):
    db.session.add(ValueSnapshot(player_id=pid, source_key=source, league_format=fmt,
                                 metric_key=metric, metric_value=value, config_key=cfg,
                                 as_of=as_of))


def _values(metric="value", pid=1):
    return [r.metric_value for r in db.session.execute(
        select(ValueSnapshot).filter_by(player_id=pid, metric_key=metric)
        .order_by(ValueSnapshot.as_of)).scalars()]


def test_policy_keeps_full_history_only_for_value():
    assert metric_policy("value") == "full"
    for m in ("redraft_value", "trade_frequency", "trend_30day", "volatility", "proj_week", "proj_ros"):
        assert metric_policy(m) == "latest_only"


def test_old_value_history_downsamples_to_latest_per_day(app_context):
    old = NOW - timedelta(days=40)
    _add(1, "value", 100.0, old.replace(hour=1))
    _add(1, "value", 101.0, old.replace(hour=9))
    _add(1, "value", 102.0, old.replace(hour=23))
    _add(1, "value", 200.0, old + timedelta(days=1))
    # other config / format are separate keys, each keeps its own row that day
    _add(1, "value", 300.0, old.replace(hour=2), cfg="12-2-1.0")
    _add(1, "value", 400.0, old.replace(hour=2), fmt="1qb", cfg="12-1-0.5")
    db.session.commit()

    report = prune_value_snapshots(dry_run=False, now=NOW)

    assert report.total == 2
    assert sorted(_values()) == [102.0, 200.0, 300.0, 400.0]
    cfg_05 = db.session.execute(select(ValueSnapshot.metric_value).filter_by(
        player_id=1, config_key="12-2-0.5", league_format="superflex")
        .order_by(ValueSnapshot.as_of)).scalars().all()
    assert cfg_05 == [102.0, 200.0]


def test_recent_value_history_is_untouched(app_context):
    recent = NOW - timedelta(days=3)
    for h in (1, 5, 9, 13):
        _add(1, "value", float(h), recent.replace(hour=h))
    db.session.commit()

    report = prune_value_snapshots(dry_run=False, now=NOW)

    assert report.total == 0
    assert _values() == [1.0, 5.0, 9.0, 13.0]


def test_latest_only_metrics_keep_one_row_per_key(app_context):
    for d in (60, 10, 1):
        _add(1, "trade_frequency", float(d), NOW - timedelta(days=d))
        _add(1, "proj_week", float(d), NOW - timedelta(days=d), source="sleeper_proj", cfg=None)
    db.session.commit()

    prune_value_snapshots(dry_run=False, now=NOW)

    assert _values("trade_frequency") == [1.0]
    assert _values("proj_week") == [1.0]


def test_dry_run_reports_without_deleting(app_context):
    for d in (5, 2):
        _add(1, "volatility", float(d), NOW - timedelta(days=d))
    db.session.commit()

    report = prune_value_snapshots(dry_run=True, now=NOW)

    assert report.deleted == {"fantasycalc/superflex/volatility": 1}
    assert db.session.scalar(select(func.count()).select_from(ValueSnapshot)) == 2


def test_prune_is_idempotent(app_context):
    old = NOW - timedelta(days=45)
    for h in (1, 2, 3):
        _add(1, "value", float(h), old.replace(hour=h))
        _add(1, "redraft_value", float(h), old.replace(hour=h))
    db.session.commit()

    first = prune_value_snapshots(dry_run=False, now=NOW)
    second = prune_value_snapshots(dry_run=False, now=NOW)

    assert first.total == 4
    assert second.total == 0
    assert db.session.scalar(select(func.count()).select_from(ValueSnapshot)) == 2


def test_latest_player_values_unchanged_by_pruning(app_context):
    for d in (90, 40, 20, 1):
        t = NOW - timedelta(days=d)
        _add(1, "value", 1000.0 + d, t)
        for m in ("redraft_value", "trade_frequency", "trend_30day", "volatility"):
            _add(1, m, float(d), t)
        _add(1, "value", 900.0 + d, t, source="ktc", cfg=None)
        _add(1, "proj_week", float(d), t, source="sleeper_proj", cfg=None)
    db.session.commit()

    before = latest_player_values("superflex", fc_config_key="12-2-0.5")
    before_nocfg = latest_player_values("superflex")
    prune_value_snapshots(dry_run=False, now=NOW)

    assert latest_player_values("superflex", fc_config_key="12-2-0.5") == before
    assert latest_player_values("superflex") == before_nocfg
    assert before[1]["sources"]["fantasycalc"]["trade_frequency"] == 1.0
    assert before[1]["projection"]["proj_week"] == 1.0
