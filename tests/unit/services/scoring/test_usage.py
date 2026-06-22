"""Usage metrics derived from raw Sleeper weekly stat lines."""
from __future__ import annotations

from services.scoring.usage import season_usage


def _wk(week, **kw):
    base = {"gp": 1.0}
    base.update(kw)
    return (week, base)


def test_season_usage_snap_share_and_volume():
    weeks = [
        _wk(1, off_snp=40, tm_off_snp=60, rec_tgt=8, rush_att=2, rec_air_yd=90, rec_rz_tgt=1, gs=1),
        _wk(2, off_snp=54, tm_off_snp=60, rec_tgt=10, rush_att=0, rec_air_yd=120, rush_rz_att=1, gs=1),
        _wk(3, off_snp=57, tm_off_snp=60, rec_tgt=12, rush_att=1, rec_air_yd=130, rec_rz_tgt=2, gs=1),
    ]
    u = season_usage(weeks)
    assert u is not None
    # season snap share = mean of 66.7, 90.0, 95.0
    assert u["snap_pct"] == 83.9
    assert u["snap_pct_l3"] == 83.9
    assert u["targets_per_game"] == 10.0
    assert u["rz_opps"] == 4
    assert u["games_started"] == 3
    assert u["air_yards_per_game"] == 113.3


def test_season_usage_skips_unplayed_weeks():
    weeks = [
        _wk(1, off_snp=50, tm_off_snp=50, rec_tgt=6),
        (2, {"gp": 0.0, "off_snp": 0, "tm_off_snp": 60}),  # inactive — ignored
    ]
    u = season_usage(weeks)
    assert u["snap_pct"] == 100.0
    assert u["targets_per_game"] == 6.0


def test_season_usage_none_without_games():
    assert season_usage([(1, {"gp": 0.0})]) is None
    assert season_usage([]) is None


def test_season_usage_omits_snap_when_team_snaps_missing():
    u = season_usage([_wk(1, rec_tgt=5)])
    assert u is not None
    assert "snap_pct" not in u
    assert u["targets_per_game"] == 5.0
