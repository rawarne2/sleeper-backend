"""compute_team_needs tests."""
from services.trade_analyzer.team_needs import compute_team_needs


def _player(name, pos, age):
    return {"name": name, "age": age, "position": pos}


def test_starter_slots_required_handles_flex_and_super_flex():
    needs = compute_team_needs([], roster_positions=["QB","RB","RB","WR","FLEX","SUPER_FLEX","BN"])
    req = needs["starter_slots_required"]
    assert req["QB"] == 1
    assert req["RB"] == 2
    assert req["WR"] == 1
    assert req["FLEX"] == 1
    assert req["SUPER_FLEX"] == 1


def test_skips_bench_taxi_ir():
    needs = compute_team_needs([], roster_positions=["QB","BN","TAXI","IR"])
    assert needs["starter_slots_required"]["QB"] == 1
    assert "BN" not in needs["starter_slots_required"]


def test_starter_eligible_count():
    players = [
        _player("a", "QB", 25), _player("b", "QB", 28),
        _player("c", "RB", 23), _player("d", "WR", 26),
    ]
    needs = compute_team_needs(players, roster_positions=["QB","RB","WR","FLEX"])
    assert needs["starter_eligible_count"]["QB"] == 2
    assert needs["starter_eligible_count"]["RB"] == 1


def test_scarcity_signal_when_no_real_depth():
    players = [_player("te1", "TE", 28)]
    needs = compute_team_needs(players, roster_positions=["TE", "FLEX"])
    assert any("TE" in s for s in needs["scarcity_signals"])


def test_age_profile_now_window():
    players = [_player(f"p{i}", "RB", 26) for i in range(5)]
    needs = compute_team_needs(players, roster_positions=["RB","RB","RB","RB","RB"])
    assert needs["age_profile"]["contention_window"] == "now"


def test_age_profile_rebuild_window():
    players = [_player(f"p{i}", "RB", 22) for i in range(5)]
    needs = compute_team_needs(players, roster_positions=["RB","RB","RB","RB","RB"])
    assert needs["age_profile"]["contention_window"] == "rebuild"


def test_age_profile_transition_window():
    players = [_player(f"p{i}", "RB", 31) for i in range(5)]
    needs = compute_team_needs(players, roster_positions=["RB","RB","RB","RB","RB"])
    assert needs["age_profile"]["contention_window"] == "transition"
