"""compute_team_needs tests."""
from services.trade_analyzer.team_needs import (
    _starter_slots,
    compute_post_trade_snapshot,
    compute_team_needs,
    compute_trade_impact,
)


def _player(name, pos, age):
    return {"name": name, "age": age, "position": pos}


def test_starter_slots_helper_handles_flex_and_super_flex():
    """starter_slots_required moved to league-wide _starter_slots (deduped from team_needs)."""
    req = _starter_slots(["QB", "RB", "RB", "WR", "FLEX", "SUPER_FLEX", "BN"])
    assert req["QB"] == 1
    assert req["RB"] == 2
    assert req["WR"] == 1
    assert req["FLEX"] == 1
    assert req["SUPER_FLEX"] == 1


def test_starter_slots_helper_skips_bench_taxi_ir():
    req = _starter_slots(["QB", "BN", "TAXI", "IR"])
    assert req["QB"] == 1
    assert "BN" not in req


def test_team_needs_omits_starter_slots_required():
    needs = compute_team_needs([], roster_positions=["QB", "RB", "BN"])
    assert "starter_slots_required" not in needs


def test_starter_eligible_count():
    players = [
        _player("a", "QB", 25), _player("b", "QB", 28),
        _player("c", "RB", 23), _player("d", "WR", 26),
    ]
    needs = compute_team_needs(players, roster_positions=["QB", "RB", "WR", "FLEX"])
    assert needs["starter_eligible_count"]["QB"] == 2
    assert needs["starter_eligible_count"]["RB"] == 1
    assert "depth_score" not in needs


def test_scarcity_signal_when_no_real_depth():
    players = [_player("te1", "TE", 28)]
    needs = compute_team_needs(players, roster_positions=["TE", "FLEX"])
    assert any("TE" in s for s in needs["scarcity_signals"])


def test_age_profile_now_window():
    players = [_player(f"p{i}", "RB", 26) for i in range(5)]
    needs = compute_team_needs(players, roster_positions=["RB", "RB", "RB", "RB", "RB"])
    assert needs["age_profile"]["contention_window"] == "now"


def test_age_profile_rebuild_window():
    players = [_player(f"p{i}", "RB", 22) for i in range(5)]
    needs = compute_team_needs(players, roster_positions=["RB", "RB", "RB", "RB", "RB"])
    assert needs["age_profile"]["contention_window"] == "rebuild"


def test_age_profile_transition_window():
    players = [_player(f"p{i}", "RB", 31) for i in range(5)]
    needs = compute_team_needs(players, roster_positions=["RB", "RB", "RB", "RB", "RB"])
    assert needs["age_profile"]["contention_window"] == "transition"


def test_trade_impact_detects_depth_change():
    before = [_player("a", "QB", 25), _player("b", "QB", 28)]
    after = [_player("a", "QB", 25)]
    impact = compute_trade_impact(before, after, side_label="side_a")
    assert any("loses QB" in s for s in impact)


def test_post_trade_snapshot_shape():
    players = [_player("a", "RB", 24), _player("b", "RB", 25)]
    snap = compute_post_trade_snapshot(players, roster_positions=["RB", "RB", "FLEX"])
    assert "starter_eligible_count" in snap
    assert "scarcity_signals" in snap
