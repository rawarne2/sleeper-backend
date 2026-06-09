from services.trade_analyzer.rag.query import build_rag_query


def test_build_rag_query_includes_format_and_windows():
    context = {
        "league": {"ktc": {"league_format": "superflex", "is_redraft": False, "tep_level": ""}},
        "side_a": {"posture": "contending", "team_needs_signals": {"age_profile": {"contention_window": "now"}}},
        "side_b": {"posture": "tanking", "team_needs_signals": {"age_profile": {"contention_window": "rebuild"}}},
        "trade": {
            "consensus_totals": {"side_a": {"net": 500}, "side_b": {"net": -500}},
            "side_a_outgoing": [{"name": "WR1", "position": "WR"}],
            "side_a_incoming": [{"name": "2027 1st", "position": "PICK"}],
            "side_b_outgoing": [{"name": "2027 1st", "position": "PICK"}],
            "side_b_incoming": [{"name": "WR1", "position": "WR"}],
        },
    }
    q = build_rag_query(context, {"season": "2026"})
    assert "superflex" in q
    assert "now" in q
    assert "rebuild" in q
    assert "500" in q
