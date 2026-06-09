from evals.trade_analyzer.run_eval import run_rag_eval


def test_run_rag_eval_report_keys(monkeypatch):
    monkeypatch.setattr(
        "evals.trade_analyzer.run_eval._run_live_echo_case",
        lambda case, league_fixture: {
            "id": case["id"],
            "status_code": 200,
            "structural_valid": True,
            "winner_match": True,
        },
    )
    report = run_rag_eval(league_fixture={})
    assert "gold_winner_match_rate_baseline" in report
    assert "gold_winner_match_rate_rag" in report
    assert "structural_validity_rate_baseline" in report
    assert "structural_validity_rate_rag" in report
