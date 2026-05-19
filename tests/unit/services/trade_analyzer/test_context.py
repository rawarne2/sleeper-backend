"""Context builder tests."""
import pytest

from services.trade_analyzer.context import build_context


@pytest.fixture(autouse=True)
def _stub_owned_picks(monkeypatch):
    monkeypatch.setattr(
        "services.trade_analyzer.context.compute_owned_picks",
        lambda lid: {},
    )


@pytest.fixture(autouse=True)
def _stub_ownership(monkeypatch):
    monkeypatch.setattr(
        "services.trade_analyzer.context._load_ownership_and_meta",
        lambda *a, **k: ({}, {}),
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
    league_fixture["total_rosters"] = 2
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    assert "league_id" not in ctx["league"]
    assert ctx["league"]["season"] == "2026"
    assert ctx["league"]["ktc"]["league_format"] == "superflex"
    assert ctx["league"]["is_dynasty"] is True
    assert ctx["league"]["total_rosters"] == 2
    assert ctx["league"]["roster_positions"][0] == "QB"
    assert "scoring_format_summary" in ctx["league"]


def test_context_groups_each_side_by_position(league_fixture):
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    assert "QB" in ctx["side_a"]["roster_by_position"]
    rb = ctx["side_b"]["roster_by_position"].get("RB", [])
    assert any(p["name"] == "Bijan Robinson" for p in rb)


def test_context_player_block_keys_are_explicit(league_fixture):
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    qb = ctx["side_a"]["roster_by_position"]["QB"][0]
    assert set(qb.keys()) == {
        "name", "position", "team", "age", "years_exp", "ktc_value",
        "positional_rank", "positional_tier", "games_played", "avg_points",
        "trajectory", "trend", "market_owned_pct", "market_started_pct",
        "injury_status", "status",
    }
    assert qb["positional_tier"] == "QB1"
    assert qb["team"] == "BUF"


def test_context_roster_injury_status_propagates(league_fixture):
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    rbs = ctx["side_b"]["roster_by_position"]["RB"]
    injured = next(p for p in rbs if p["name"] == "Christian McCaffrey")
    assert injured["injury_status"] == "Out"
    assert injured["status"] == "Inactive"
    healthy_trade = ctx["trade"]["side_b_outgoing"][0]
    assert healthy_trade["name"] == "Bijan Robinson"
    assert healthy_trade["injury_status"] is None
    assert healthy_trade["status"] is None


def test_context_records_trimmed_record(league_fixture):
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    assert ctx["side_a"]["record"]["wins"] == 2
    assert ctx["side_b"]["record"]["fpts"] == 380.0
    assert "roster_id" not in ctx["side_a"]


def test_context_roster_and_trade_include_market_pct(league_fixture, monkeypatch):
    monkeypatch.setattr(
        "services.trade_analyzer.context._load_ownership_and_meta",
        lambda *a, **k: (
            {
                "4881": {"owned": 42.5, "started": 31.0},
                "4034": {"owned": 88.0, "started": 72.5},
            },
            {},
        ),
    )
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    roster_qb = ctx["side_a"]["roster_by_position"]["QB"][0]
    assert roster_qb["market_owned_pct"] == 42.5
    assert roster_qb["market_started_pct"] == 31.0
    trade_out = ctx["trade"]["side_b_outgoing"][0]
    assert trade_out["market_owned_pct"] == 88.0
    assert trade_out["market_started_pct"] == 72.5


def test_context_trade_assets_and_totals(league_fixture):
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    out = ctx["trade"]["side_a_outgoing"][0]
    assert out["name"] == "Josh Allen"
    assert out["kind"] == "player"
    assert out["position"] == "QB"
    assert "injury_status" in out
    assert ctx["trade"]["side_b_outgoing"][0]["name"] == "Bijan Robinson"
    a = ctx["trade"]["ktc_totals"]["side_a"]
    b = ctx["trade"]["ktc_totals"]["side_b"]
    assert a["out"] == 9120
    assert a["in"] == 8200
    assert a["net"] == -920
    assert b["out"] == 8200
    assert b["in"] == 9120
    assert b["net"] == 920


def test_context_trade_summary(league_fixture):
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    assert "Josh Allen" in ctx["trade_summary"]["side_a_gives"]
    assert ctx["trade_summary"]["ktc_net"]["side_a"] == -920


def test_context_omits_additional_context_in_json(league_fixture):
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    assert "additional_context" not in ctx


def test_context_includes_post_trade_fields(league_fixture):
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    assert "after_trade_snapshot" in ctx["side_a"]
    assert "trade_impact" in ctx["side_a"]
    assert "depth_score" not in ctx["side_a"]["team_needs_signals"]


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
    req = {
        "league_id": "1210364682523656192", "season": "2026",
        "ktc": {"league_format": "superflex", "is_redraft": False, "tep_level": "tep"},
        "side_a": {"roster_id": 3, "player_ids": ["4881"], "pick_ids": ["2026-r1-mid"]},
        "side_b": {"roster_id": 7, "player_ids": ["4034"], "pick_ids": []},
    }
    ctx = build_context(req, league_data=league_fixture)
    owned = ctx["side_a"]["owned_picks"][0]
    assert owned["pick_id"] == "2026-r1-mid"
    assert owned["season"] == "2026"
    assert owned["round"] == 1
    assert owned["slot"] == "mid"
    assert "label" in owned
    assert any(asset.get("kind") == "pick" for asset in ctx["trade"]["side_a_outgoing"])


def test_context_400_on_unparseable_pick(league_fixture, monkeypatch):
    monkeypatch.setattr(
        "services.trade_analyzer.context.compute_owned_picks",
        lambda lid: {3: [], 7: []},
    )
    req = {
        "league_id": "1210364682523656192", "season": "2026",
        "ktc": {"league_format": "superflex", "is_redraft": False, "tep_level": "tep"},
        "side_a": {"roster_id": 3, "player_ids": ["4881"], "pick_ids": ["garbage"]},
        "side_b": {"roster_id": 7, "player_ids": ["4034"], "pick_ids": []},
    }
    with pytest.raises(ValueError):
        build_context(req, league_data=league_fixture)


def test_context_includes_team_needs_signals(league_fixture):
    req = {
        "league_id": "1210364682523656192", "season": "2026",
        "ktc": {"league_format": "superflex", "is_redraft": False, "tep_level": "tep"},
        "side_a": {"roster_id": 3, "player_ids": ["4881"], "pick_ids": []},
        "side_b": {"roster_id": 7, "player_ids": ["4034"], "pick_ids": []},
    }
    ctx = build_context(req, league_data=league_fixture)
    needs = ctx["side_a"]["team_needs_signals"]
    assert "starter_slots_required" in needs
    assert "age_profile" in needs
