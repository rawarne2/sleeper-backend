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


def test_build_context_skips_ownership_query_when_threaded(monkeypatch, league_fixture):
    """When league_data carries ownership + research_meta, build_context must not requery."""
    from services.trade_analyzer import context as ctx_mod

    calls = {"n": 0}

    def _spy(*args, **kwargs):
        calls["n"] += 1
        return ({}, {})

    monkeypatch.setattr(ctx_mod, "_load_ownership_and_meta", _spy)
    league_data = dict(league_fixture)
    league_data["ownership"] = {}
    league_data["research_meta"] = {"week": 12, "season": "2026"}

    req = {
        "league_id": "1210364682523656192",
        "season": "2026",
        "ktc": {"league_format": "superflex", "is_redraft": False, "tep_level": "tep"},
        "side_a": {"roster_id": 3, "player_ids": ["4881"], "pick_ids": []},
        "side_b": {"roster_id": 7, "player_ids": ["4034"], "pick_ids": []},
        "additional_context": None,
        "provider": "echo",
        "model": "echo",
    }

    out = build_context(req, league_data=league_data)
    assert out["league"]["research_week"] == 12
    assert calls["n"] == 0, (
        "build_context must reuse threaded ownership instead of querying again"
    )


def _req(side_a_players, side_b_players, *, side_a_tanking=False, side_b_tanking=False):
    return {
        "league_id": "1210364682523656192",
        "season": "2026",
        "ktc": {"league_format": "superflex", "is_redraft": False, "tep_level": "tep"},
        "side_a": {
            "roster_id": 3, "player_ids": side_a_players, "pick_ids": [],
            "is_tanking": side_a_tanking,
        },
        "side_b": {
            "roster_id": 7, "player_ids": side_b_players, "pick_ids": [],
            "is_tanking": side_b_tanking,
        },
        "additional_context": "rebuild mode",
        "provider": "echo", "model": "echo",
    }


def test_context_emits_contending_posture_by_default(league_fixture):
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    assert ctx["side_a"]["posture"] == "contending"
    assert ctx["side_b"]["posture"] == "contending"


def test_context_emits_tanking_posture_when_set(league_fixture):
    ctx = build_context(
        _req(["4881"], ["4034"], side_a_tanking=True),
        league_data=league_fixture,
    )
    assert ctx["side_a"]["posture"] == "tanking"
    assert ctx["side_b"]["posture"] == "contending"


def test_context_includes_league_block(league_fixture):
    league_fixture["total_rosters"] = 2
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    assert "league_id" not in ctx["league"]
    assert ctx["league"]["season"] == "2026"
    assert ctx["league"]["ktc"]["league_format"] == "superflex"
    assert ctx["league"]["total_rosters"] == 2
    assert ctx["league"]["starter_slots_required"]["QB"] == 1
    assert ctx["league"]["bench_slots"] == 6
    assert "roster_positions" not in ctx["league"]
    assert "is_dynasty" not in ctx["league"]
    assert ctx["league"]["league_type"] == "dynasty"
    assert "scoring_format_summary" in ctx["league"]


def test_context_omits_roster_by_position(league_fixture):
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    assert "roster_by_position" not in ctx["side_a"]
    assert "QB" in ctx["side_a"]["roster"]["starters"]


def test_context_roster_player_is_slim(league_fixture):
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    qb = ctx["side_a"]["roster"]["starters"]["QB"][0]
    assert set(qb.keys()) <= {
        "name", "ktc_value", "positional_rank", "age",
        "injury_status", "injury", "ktc_injury",
        "market_owned_pct", "market_started_pct",
    }
    assert qb["name"] == "Josh Allen"
    assert "position" not in qb
    assert "positional_tier" not in qb
    assert "market_owned_pct" not in qb
    assert qb["ktc_value"] == 9120
    assert qb["positional_rank"] == 1
    assert "ktc" not in qb


def test_context_trade_player_includes_ktc_extras(league_fixture):
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    qb = ctx["trade"]["side_a_outgoing"][0]
    assert qb["positional_tier"] == "QB1"
    assert qb["ktc_value"] == 9120
    assert qb["positional_rank"] == 1
    assert qb["trend"] == 150
    ktc = qb.get("ktc") or {}
    # ktc subblock should NOT duplicate top-level fields
    assert "value" not in ktc
    assert "positionalRank" not in ktc
    assert "overallTrend" not in ktc
    assert "overallTrendFormatted" not in ktc
    assert "tep" not in ktc
    assert "tepp" not in ktc
    assert "teppp" not in ktc
    assert "research" not in qb


def test_context_trade_player_omits_empty_fields(league_fixture):
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    healthy = ctx["trade"]["side_b_outgoing"][0]
    assert healthy["name"] == "Bijan Robinson"
    assert "injury" not in healthy
    assert "practice" not in healthy
    assert "is_starter_latest" not in healthy


def test_context_roster_includes_all_bench_positions(league_fixture):
    league_fixture["rosters"][0]["taxi"] = ["4017"]
    league_fixture["rosters"][0]["reserve"] = []
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    roster = ctx["side_a"]["roster"]
    taxi_values = [p["ktc_value"] for plist in roster["taxi"].values() for p in plist]
    assert 8800 in taxi_values
    bench_rb = ctx["side_b"]["roster"]["bench"].get("RB", [])
    assert any(p["ktc_value"] == 6800 for p in bench_rb)


def test_context_roster_injury_status_on_roster_and_trade(league_fixture):
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    assert "roster_by_position" not in ctx["side_b"]
    starter = ctx["side_b"]["roster"]["starters"]["RB"][0]
    assert starter["ktc_value"] == 8200
    assert "injury_status" not in starter
    bench_injured = next(
        p for plist in ctx["side_b"]["roster"]["bench"].values() for p in plist
        if p["ktc_value"] == 6800
    )
    assert bench_injured["injury_status"] == "Out"


def test_context_records_only_when_meaningful(league_fixture):
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    assert ctx["side_a"]["record"]["wins"] == 2
    assert ctx["side_b"]["record"]["fpts"] == 380.0
    assert "roster_id" not in ctx["side_a"]


def test_context_always_includes_record(league_fixture):
    league_fixture["rosters"][0]["settings"] = {
        "wins": 0, "losses": 0, "ties": 0, "fpts": 0,
    }
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    assert ctx["side_a"]["record"] == {
        "wins": 0, "losses": 0, "ties": 0, "fpts": 0,
    }


def test_context_roster_name_with_int_sleeper_id_index(league_fixture, monkeypatch):
    """Player index keys must be str so trade roster rows still get names."""
    monkeypatch.setattr(
        "services.trade_analyzer.context.compute_owned_picks",
        lambda lid: {3: [], 7: []},
    )
    for p in league_fixture["players"]:
        if p["sleeper_player_id"] == "4881":
            p["sleeper_player_id"] = 4881
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    qb = ctx["side_a"]["roster"]["starters"]["QB"][0]
    assert qb["name"] == "Josh Allen"
    assert ctx["trade"]["side_a_outgoing"][0]["name"] == "Josh Allen"


def test_context_roster_omits_name_for_non_trade_players(league_fixture):
    league_fixture["rosters"][0]["taxi"] = ["4017"]
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    taxi_qb = ctx["side_a"]["roster"]["taxi"]["QB"][0]
    assert "name" not in taxi_qb
    trade_qb = ctx["side_a"]["roster"]["starters"]["QB"][0]
    assert trade_qb["name"] == "Josh Allen"


def test_context_roster_and_trade_include_market_pct(league_fixture, monkeypatch):
    monkeypatch.setattr(
        "services.trade_analyzer.context._load_ownership_and_meta",
        lambda *a, **k: (
            {
                "4881": {"owned": 42.5, "started": 31.0},
                "4034": {"owned": 88.0, "started": 72.5},
            },
            {"week": 3},
        ),
    )
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    assert ctx["league"]["research_week"] == 3
    roster_qb = ctx["side_a"]["roster"]["starters"]["QB"][0]
    assert roster_qb["name"] == "Josh Allen"
    assert roster_qb["market_owned_pct"] == 42.5
    assert roster_qb["market_started_pct"] == 31.0
    trade_out = ctx["trade"]["side_b_outgoing"][0]
    assert trade_out["market_owned_pct"] == 88.0
    assert trade_out["market_started_pct"] == 72.5
    assert "research" not in trade_out


def test_context_trade_assets_and_totals(league_fixture):
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    out = ctx["trade"]["side_a_outgoing"][0]
    assert out["name"] == "Josh Allen"
    assert out["kind"] == "player"
    assert out["position"] == "QB"
    assert ctx["trade"]["side_b_outgoing"][0]["name"] == "Bijan Robinson"
    a = ctx["trade"]["consensus_totals"]["side_a"]
    b = ctx["trade"]["consensus_totals"]["side_b"]
    assert a["out"] == 9120
    assert a["in"] == 8200
    assert a["net"] == -920
    assert b["out"] == 8200
    assert b["in"] == 9120
    assert b["net"] == 920


def test_context_includes_explicit_incoming_assets(league_fixture):
    """side_*_incoming mirrors the other side's outgoing so each direction is unambiguous."""
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    assert "trade_summary" not in ctx
    assert ctx["trade"]["side_a_incoming"] == ctx["trade"]["side_b_outgoing"]
    assert ctx["trade"]["side_b_incoming"] == ctx["trade"]["side_a_outgoing"]
    assert ctx["trade"]["consensus_totals"]["side_a"]["net"] == -920


def test_context_omits_additional_context_in_json(league_fixture):
    ctx = build_context(_req(["4881"], ["4034"]), league_data=league_fixture)
    assert "additional_context" not in ctx


def test_player_trade_emits_consensus_value_from_values_block():
    """consensus_value comes from values.consensus; ktc_value stays the KTC number."""
    from services.trade_analyzer.context import _player_trade

    player = {
        "player_name": "Test WR",
        "position": "WR",
        "sleeper_player_id": "999",
        "ktc": {"superflexValues": {"value": 7000, "positionalRank": 5}, "age": 24},
        "values": {"consensus": 7250.0, "sources": {}, "projection": {}},
    }
    out = _player_trade(player, "superflex", None)
    assert out["consensus_value"] == 7250.0
    assert out["ktc_value"] == 7000
    assert "team" not in out
    assert "is_starter_latest" not in out


def test_player_trade_emits_stats_prev_when_present():
    """stats_prev (previous-season aggregates) is surfaced on the trade asset."""
    from services.trade_analyzer.context import _player_trade

    player = {
        "player_name": "Test RB",
        "position": "RB",
        "sleeper_player_id": "888",
        "ktc": {"superflexValues": {"value": 5000, "positionalRank": 10}, "age": 25},
        "stats_prev": {"average_points": 15.2, "total_points": 258.0, "games_played": 17},
    }
    out = _player_trade(player, "superflex", None)
    assert out["stats_prev"]["games_played"] == 17
    assert out["stats_prev"]["average_points"] == 15.2


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
    assert owned["kind"] == "pick"
    assert "pick_id" not in owned
    assert "season" not in owned
    assert "round" not in owned
    assert "slot" not in owned
    assert owned["label"] == "2026 Mid 1st"
    pick_out = next(a for a in ctx["trade"]["side_a_outgoing"] if a.get("kind") == "pick")
    assert pick_out["label"] == owned["label"]
    assert "pick_id" not in pick_out


def test_context_dedupes_owned_picks(league_fixture, monkeypatch):
    dup = {"season": "2026", "round": 1, "original_roster_id": 3,
           "slot_bucket": "mid", "pick_id": "2026-r1-mid", "ktc_value": 4200}
    monkeypatch.setattr(
        "services.trade_analyzer.context.compute_owned_picks",
        lambda lid: {3: [dup, dup, dup], 7: []},
    )
    req = {
        "league_id": "1210364682523656192", "season": "2026",
        "ktc": {"league_format": "superflex", "is_redraft": False, "tep_level": "tep"},
        "side_a": {"roster_id": 3, "player_ids": ["4881"], "pick_ids": []},
        "side_b": {"roster_id": 7, "player_ids": ["4034"], "pick_ids": []},
    }
    ctx = build_context(req, league_data=league_fixture)
    assert len(ctx["side_a"]["owned_picks"]) == 1


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


def test_context_trade_ktc_injury_when_sleeper_healthy(league_fixture):
    league_fixture["players"].append({
        "playerName": "Dalton Kincaid",
        "sleeper_player_id": "9999",
        "position": "TE",
        "team": "BUF",
        "years_exp": 3,
        "injury_status": "",
        "status": "Active",
        "ktc": {
            "age": 26,
            "superflexValues": {"value": 3664, "positionalRank": 15},
            "injury": {
                "injuryName": "Questionable",
                "injuryCode": 2,
                "injuryArea": "Knee - PCL",
                "injuryReturn": "Jun 1, 2026",
            },
        },
        "stats": {},
    })
    league_fixture["rosters"][0]["players"].append("9999")
    req = {
        "league_id": "1210364682523656192",
        "season": "2026",
        "ktc": {"league_format": "superflex", "is_redraft": False, "tep_level": "tep"},
        "side_a": {"roster_id": 3, "player_ids": ["9999"], "pick_ids": []},
        "side_b": {"roster_id": 7, "player_ids": ["4034"], "pick_ids": []},
    }
    ctx = build_context(req, league_data=league_fixture)
    te = ctx["trade"]["side_a_outgoing"][0]
    assert te["name"] == "Dalton Kincaid"
    assert te["injury_status"] == "Questionable"
    assert "injury" not in te
    assert te["ktc"]["injury"]["injuryName"] == "Questionable"
    assert "tep" not in te["ktc"]


def test_context_trade_sleeper_injury_without_ktc_injury(league_fixture):
    league_fixture["players"].append({
        "playerName": "Hurt Player",
        "sleeper_player_id": "8888",
        "position": "RB",
        "team": "SF",
        "years_exp": 5,
        "injury_status": "Out",
        "status": "Inactive",
        "injury_body_part": "Knee",
        "ktc": {
            "age": 28,
            "superflexValues": {"value": 1000, "positionalRank": 50},
            "injury": {"injuryCode": 1},
        },
        "stats": {},
    })
    req = {
        "league_id": "1210364682523656192",
        "season": "2026",
        "ktc": {"league_format": "superflex", "is_redraft": False, "tep_level": "tep"},
        "side_a": {"roster_id": 3, "player_ids": ["8888"], "pick_ids": []},
        "side_b": {"roster_id": 7, "player_ids": ["4034"], "pick_ids": []},
    }
    ctx = build_context(req, league_data=league_fixture)
    rb = ctx["trade"]["side_a_outgoing"][0]
    assert rb["injury_status"] == "Out"
    assert rb["status"] == "Inactive"
    assert rb["injury"]["status"] == "Out"
    assert rb["injury"]["body_part"] == "Knee"
    # Healthy-only KTC injuryCode 1 and no extra value keys → nested ktc omitted
    assert "ktc" not in rb


def test_context_roster_uses_ktc_injury_name_when_sleeper_blank(league_fixture):
    league_fixture["players"].append({
        "playerName": "Dalton Kincaid",
        "sleeper_player_id": "9999",
        "position": "TE",
        "team": "BUF",
        "injury_status": "",
        "ktc": {
            "age": 26,
            "superflexValues": {"value": 3664, "positionalRank": 15},
            "injury": {"injuryName": "Questionable", "injuryCode": 2},
        },
    })
    league_fixture["rosters"][0]["players"].append("9999")
    league_fixture["rosters"][0]["starters"].append("9999")
    req = {
        "league_id": "1210364682523656192",
        "season": "2026",
        "ktc": {"league_format": "superflex", "is_redraft": False, "tep_level": "tep"},
        "side_a": {"roster_id": 3, "player_ids": ["4881"], "pick_ids": []},
        "side_b": {"roster_id": 7, "player_ids": ["4034"], "pick_ids": []},
    }
    ctx = build_context(req, league_data=league_fixture)
    te = ctx["side_a"]["roster"]["starters"]["TE"][-1]
    assert te["injury_status"] == "Questionable"


def test_context_pick_only_trade_minimal_roster(league_fixture, monkeypatch):
    monkeypatch.setattr(
        "services.trade_analyzer.context.compute_owned_picks",
        lambda lid: {
            3: [{"season": "2026", "round": 1, "original_roster_id": 3,
                 "slot_bucket": "mid", "pick_id": "2026-r1-mid", "ktc_value": 4200}],
            7: [],
        },
    )
    monkeypatch.setattr(
        "services.trade_analyzer.context.resolve_pick_to_ktc",
        lambda pid, **kw: ("p", 4200),
    )
    req = {
        "league_id": "1210364682523656192", "season": "2026",
        "ktc": {"league_format": "superflex", "is_redraft": False, "tep_level": "tep"},
        "side_a": {"roster_id": 3, "player_ids": [], "pick_ids": ["2026-r1-mid"]},
        "side_b": {"roster_id": 7, "player_ids": [], "pick_ids": []},
    }
    ctx = build_context(req, league_data=league_fixture)
    assert ctx["side_a"]["roster"]["bench"] == {}
    assert "QB" in ctx["side_a"]["roster"]["starters"]


def test_context_sleeper_ir_counts_as_injury(league_fixture):
    league_fixture["players"].append({
        "playerName": "On IR",
        "sleeper_player_id": "7777",
        "position": "RB",
        "team": "NYG",
        "injury_status": "IR",
        "ktc": {"age": 27, "superflexValues": {"value": 500, "positionalRank": 99}},
    })
    req = {
        "league_id": "1210364682523656192", "season": "2026",
        "ktc": {"league_format": "superflex", "is_redraft": False, "tep_level": "tep"},
        "side_a": {"roster_id": 3, "player_ids": ["7777"], "pick_ids": []},
        "side_b": {"roster_id": 7, "player_ids": ["4034"], "pick_ids": []},
    }
    ctx = build_context(req, league_data=league_fixture)
    assert ctx["trade"]["side_a_outgoing"][0]["injury_status"] == "IR"


def test_context_includes_team_needs_signals(league_fixture):
    req = {
        "league_id": "1210364682523656192", "season": "2026",
        "ktc": {"league_format": "superflex", "is_redraft": False, "tep_level": "tep"},
        "side_a": {"roster_id": 3, "player_ids": ["4881"], "pick_ids": []},
        "side_b": {"roster_id": 7, "player_ids": ["4034"], "pick_ids": []},
    }
    ctx = build_context(req, league_data=league_fixture)
    needs = ctx["side_a"]["team_needs_signals"]
    # starter_slots_required is league-wide; it lives on league.starter_slots_required only
    assert "starter_slots_required" not in needs
    assert ctx["league"]["starter_slots_required"]["QB"] == 1
    assert "starter_eligible_count" in needs
    assert "scarcity_signals" in needs
    assert "age_profile" in needs
