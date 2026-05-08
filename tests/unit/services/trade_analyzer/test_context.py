"""Context builder tests."""
import pytest

from services.trade_analyzer.context import build_context


@pytest.fixture(autouse=True)
def _stub_owned_picks(monkeypatch):
    monkeypatch.setattr(
        "services.trade_analyzer.context.compute_owned_picks",
        lambda lid: {},
    )


def _req(side_a_players, side_b_players):
    return {
        "league_id": "1210364682523656192",
        "season": "2026",
        "ktc": {"league_format": "superflex", "is_redraft": False, "tep_level": "tep"},
        "side_a": {"roster_id": 3, "player_ids": side_a_players, "pick_ids": []},
        "side_b": {"roster_id": 7, "player_ids": side_b_players, "pick_ids": []},
        "additional_context": "rebuild mode",
        "provider": "echo", "model": "echo",
    }


def test_context_includes_league_block(league_fixture):
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    assert ctx["league"]["league_id"] == "1210364682523656192"
    assert ctx["league"]["season"] == "2026"
    assert ctx["league"]["ktc"]["league_format"] == "superflex"
    assert ctx["league"]["roster_positions"][0] == "QB"
    assert "scoring_format_summary" in ctx["league"]


def test_context_groups_each_side_by_position(league_fixture):
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    assert "QB" in ctx["side_a"]["roster_by_position"]
    rb = ctx["side_b"]["roster_by_position"].get("RB", [])
    assert any(p["name"] == "Bijan Robinson" for p in rb)


def test_context_player_block_keys_are_minimal(league_fixture):
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    qb = ctx["side_a"]["roster_by_position"]["QB"][0]
    assert set(qb.keys()) == {
        "name", "age", "years_exp", "ktc_value",
        "positional_rank", "games_played", "avg_points",
        "trajectory", "trend",
    }


def test_context_records_record_block(league_fixture):
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    assert ctx["side_a"]["record"]["wins"] == 2
    assert ctx["side_b"]["record"]["fpts"] == 380.0


def test_context_trade_assets_and_totals(league_fixture):
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    assert ctx["trade"]["side_a_outgoing"][0]["name"] == "Josh Allen"
    assert ctx["trade"]["side_b_outgoing"][0]["name"] == "Bijan Robinson"
    a = ctx["trade"]["ktc_totals"]["side_a"]
    b = ctx["trade"]["ktc_totals"]["side_b"]
    assert a["out"] == 9120
    assert a["in"] == 8200
    assert a["net"] == -920
    assert b["out"] == 8200
    assert b["in"] == 9120
    assert b["net"] == 920


def test_context_passes_additional_context_through(league_fixture):
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    assert ctx["additional_context"] == "rebuild mode"


def test_context_400_when_unknown_roster(league_fixture):
    body = _req(["4881"], ["4034"])
    body["side_a"]["roster_id"] = 999
    with pytest.raises(ValueError, match="roster_id"):
        build_context(body, league_data=league_fixture)


def test_context_400_when_unknown_player(league_fixture):
    body = _req(["nope"], ["4034"])
    with pytest.raises(ValueError, match="player_id"):
        build_context(body, league_data=league_fixture)


def test_context_includes_owned_picks_when_resolved(league_fixture, monkeypatch):
    fake_picks = {
        3: [{"season": "2026", "round": 1, "original_roster_id": 3,
             "slot_bucket": "mid", "pick_id": "2026-r1-mid", "ktc_value": None}],
        7: [],
    }
    monkeypatch.setattr(
        "services.trade_analyzer.context.compute_owned_picks",
        lambda lid: fake_picks,
    )
    monkeypatch.setattr(
        "services.trade_analyzer.context.resolve_pick_to_ktc",
        lambda pid, **kw: None,
    )
    from services.trade_analyzer.context import build_context
    req = {
        "league_id": "1210364682523656192", "season": "2026",
        "ktc": {"league_format": "superflex", "is_redraft": False, "tep_level": "tep"},
        "side_a": {"roster_id": 3, "player_ids": ["4881"], "pick_ids": ["2026-r1-mid"]},
        "side_b": {"roster_id": 7, "player_ids": ["4034"], "pick_ids": []},
    }
    ctx = build_context(req, league_data=league_fixture)
    assert ctx["side_a"]["owned_picks"] == [{"pick_id": "2026-r1-mid", "ktc_value": None}]
    assert any(asset.get("kind") == "pick" for asset in ctx["trade"]["side_a_outgoing"])


def test_context_400_on_unparseable_pick(league_fixture, monkeypatch):
    monkeypatch.setattr(
        "services.trade_analyzer.context.compute_owned_picks",
        lambda lid: {3: [], 7: []},
    )
    from services.trade_analyzer.context import build_context
    req = {
        "league_id": "1210364682523656192", "season": "2026",
        "ktc": {"league_format": "superflex", "is_redraft": False, "tep_level": "tep"},
        "side_a": {"roster_id": 3, "player_ids": ["4881"], "pick_ids": ["garbage"]},
        "side_b": {"roster_id": 7, "player_ids": ["4034"], "pick_ids": []},
    }
    import pytest
    with pytest.raises(ValueError):
        build_context(req, league_data=league_fixture)
