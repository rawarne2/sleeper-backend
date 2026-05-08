"""LLM response parser tests."""
import json
import pytest

from services.trade_analyzer.parser import ParseError, parse_llm_response


def _ok():
    return {
        "fairness_score": 50, "winner": "even", "summary_bullets": ["x"],
        "side_a": {"ktc_delta": {"values_in": 100, "values_out": 100, "net": 0, "per_asset": []}},
        "side_b": {"ktc_delta": {"values_in": 100, "values_out": 100, "net": 0, "per_asset": []}},
    }


def test_parses_clean_json():
    raw = '{"fairness_score": 50, "winner": "even", "summary_bullets": ["x"], "side_a": {}, "side_b": {}}'
    p = parse_llm_response(raw)
    assert p["fairness_score"] == 50


def test_strips_json_fences():
    payload = '{"fairness_score":75,"winner":"side_a","summary_bullets":["x"],"side_a":{},"side_b":{}}'
    raw = f"```json\n{payload}\n```"
    p = parse_llm_response(raw)
    assert p["fairness_score"] == 75


def test_strips_trailing_prose():
    payload = '{"fairness_score":50,"winner":"even","summary_bullets":["x"],"side_a":{},"side_b":{}}'
    raw = f"Here's the analysis: {payload}\n\nHope that helps!"
    p = parse_llm_response(raw)
    assert p["fairness_score"] == 50


def test_raises_on_invalid_json():
    with pytest.raises(ParseError):
        parse_llm_response("not json at all")


def test_raises_on_missing_required_keys():
    with pytest.raises(ParseError, match="Missing"):
        parse_llm_response('{"fairness_score": 50}')


def test_clamps_fairness_score_high():
    raw = '{"fairness_score":150,"winner":"side_a","summary_bullets":["x"],"side_a":{},"side_b":{}}'
    p = parse_llm_response(raw)
    assert p["fairness_score"] == 100


def test_clamps_fairness_score_low():
    raw = '{"fairness_score":-30,"winner":"side_b","summary_bullets":["x"],"side_a":{},"side_b":{}}'
    p = parse_llm_response(raw)
    assert p["fairness_score"] == 0


def test_infers_winner_when_invalid():
    raw = '{"fairness_score":70,"winner":"sideA","summary_bullets":["x"],"side_a":{},"side_b":{}}'
    p = parse_llm_response(raw)
    assert p["winner"] == "side_a"


def test_numeric_drift_logged_not_raised():
    payload = _ok()
    payload["side_a"]["ktc_delta"]["values_in"] = 1000
    raw = json.dumps(payload)
    p = parse_llm_response(
        raw,
        expected_totals={"side_a": {"in": 100, "out": 100, "net": 0},
                         "side_b": {"in": 100, "out": 100, "net": 0}},
    )
    assert p["side_a"]["ktc_delta"]["values_in"] == 1000
