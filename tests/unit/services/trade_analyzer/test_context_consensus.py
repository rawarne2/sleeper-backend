# tests/unit/services/trade_analyzer/test_context_consensus.py
from services.trade_analyzer.context import _consensus_totals


def test_consensus_totals_uses_blended_value():
    a_out = [{"ktc_value": 8000, "blended_value": 8000.0}]
    b_out = [{"ktc_value": 4000, "blended_value": 5000.0}]
    totals = _consensus_totals(a_out, b_out)
    assert totals["side_a"]["out"] == 8000.0
    assert totals["side_a"]["in"] == 5000.0
    assert totals["side_a"]["net"] == 5000.0 - 8000.0
    assert totals["side_b"]["net"] == 8000.0 - 5000.0


def test_consensus_totals_falls_back_to_ktc_when_blended_missing():
    a_out = [{"ktc_value": 8000}]
    b_out = [{"ktc_value": 4000}]
    totals = _consensus_totals(a_out, b_out)
    assert totals["side_a"]["out"] == 8000.0
    assert totals["side_a"]["in"] == 4000.0
