"""LLM response parser tests."""
import json
import pytest

from services.trade_analyzer.parser import ParseError, parse_llm_response

_MINIMAL = (
    '{"winner":"even","summary_bullets":["x"],"side_a":{},"side_b":{}}'
)


def _ok():
    return {
        "winner": "even",
        "summary_bullets": ["x"],
        "side_a": {"ktc_delta": {"values_in": 100, "values_out": 100, "net": 0, "per_asset": []}},
        "side_b": {"ktc_delta": {"values_in": 100, "values_out": 100, "net": 0, "per_asset": []}},
    }


def test_parses_clean_json():
    p = parse_llm_response(_MINIMAL)
    assert p["winner"] == "even"


def test_strips_unknown_top_level_keys():
    raw = (
        '{"stale_field":75,"winner":"side_a","summary_bullets":["x"],'
        '"side_a":{},"side_b":{}}'
    )
    p = parse_llm_response(raw)
    assert p["winner"] == "side_a"
    assert "stale_field" not in p


def test_strips_json_fences():
    raw = f"```json\n{_MINIMAL}\n```"
    p = parse_llm_response(raw)
    assert p["winner"] == "even"


def test_strips_trailing_prose():
    raw = f"Here's the analysis: {_MINIMAL}\n\nHope that helps!"
    p = parse_llm_response(raw)
    assert p["winner"] == "even"


def test_picks_full_object_when_prefixed_with_other_json():
    noise = '{"note":"ignore"}'
    payload = (
        '{"winner":"side_a","summary_bullets":["x"],"side_a":{},"side_b":{}}'
    )
    raw = f"{noise}\n{payload}"
    p = parse_llm_response(raw)
    assert p["winner"] == "side_a"


def test_unwraps_analysis_wrapper():
    inner = (
        '{"winner":"side_a","summary_bullets":["x"],'
        '"side_a":{},"side_b":{}}'
    )
    raw = '{"analysis": ' + inner + "}"
    p = parse_llm_response(raw)
    assert p["winner"] == "side_a"


def test_recovers_trade_details_blob():
    raw = (
        '{"trade_details": {'
        '"team_a_gain": 2172, "team_a_losing_player": "Mac Jones", '
        '"team_b_gain": -2172, "team_b_losing_player": "C.J. Stroud"'
        "}}"
    )
    totals = {
        "side_a": {"in": 100, "out": 80, "net": 20},
        "side_b": {"in": 80, "out": 100, "net": -20},
    }
    p = parse_llm_response(raw, expected_totals=totals)
    assert p["winner"] == "side_a"
    assert p["side_a"]["ktc_delta"]["net"] == 20
    assert p["side_b"]["ktc_delta"]["net"] == -20


def test_raises_on_invalid_json():
    with pytest.raises(ParseError):
        parse_llm_response("not json at all")


def test_raises_on_missing_required_keys():
    with pytest.raises(ParseError, match="Missing"):
        parse_llm_response('{"winner": "even"}')


def test_infers_winner_when_invalid():
    raw = (
        '{"winner":"sideA","summary_bullets":["x"],"side_a":{},"side_b":{}}'
    )
    totals = {
        "side_a": {"in": 100, "out": 80, "net": 20},
        "side_b": {"in": 80, "out": 100, "net": -20},
    }
    p = parse_llm_response(raw, expected_totals=totals)
    assert p["winner"] == "side_a"


def test_infers_even_when_invalid_winner_and_no_totals():
    raw = (
        '{"winner":"sideA","summary_bullets":["x"],"side_a":{},"side_b":{}}'
    )
    p = parse_llm_response(raw)
    assert p["winner"] == "even"


def test_preserves_valid_trade_grade():
    raw = (
        '{"winner":"even","summary_bullets":["x"],'
        '"side_a":{"trade_grade":"B+"},"side_b":{"trade_grade":"B-"}}'
    )
    p = parse_llm_response(raw)
    assert p["side_a"]["trade_grade"] == "B+"
    assert p["side_b"]["trade_grade"] == "B-"


def test_preserves_f_and_f_plus_grades():
    raw = (
        '{"winner":"side_b","summary_bullets":["x"],'
        '"side_a":{"trade_grade":"F+"},"side_b":{"trade_grade":"A"}}'
    )
    p = parse_llm_response(raw)
    assert p["side_a"]["trade_grade"] == "F+"
    assert p["side_b"]["trade_grade"] == "A"


def test_fallback_trade_grade_when_missing():
    raw = (
        '{"winner":"side_a","summary_bullets":["x"],"side_a":{},"side_b":{}}'
    )
    p = parse_llm_response(raw)
    assert p["side_a"]["trade_grade"] == "B+"
    assert p["side_b"]["trade_grade"] == "D+"


def test_merge_expected_ktc_when_side_blocks_empty():
    raw = (
        '{"winner":"side_a","summary_bullets":["x"],"side_a":{},"side_b":{}}'
    )
    totals = {
        "side_a": {"in": 5000, "out": 2000, "net": 3000},
        "side_b": {"in": 2000, "out": 5000, "net": -3000},
    }
    p = parse_llm_response(raw, expected_totals=totals)
    assert p["side_a"]["ktc_delta"]["values_in"] == 5000
    assert p["side_a"]["ktc_delta"]["values_out"] == 2000
    assert p["side_a"]["ktc_delta"]["net"] == 3000
    assert p["side_b"]["ktc_delta"]["net"] == -3000


def test_fallback_trade_grade_even_trade():
    p = parse_llm_response(_MINIMAL)
    assert p["side_a"]["trade_grade"] == "C"
    assert p["side_b"]["trade_grade"] == "C"


def test_fallback_trade_grade_invalid_value():
    raw = (
        '{"winner":"side_b","summary_bullets":["x"],'
        '"side_a":{"trade_grade":"garbage"},"side_b":{}}'
    )
    p = parse_llm_response(raw)
    assert p["side_a"]["trade_grade"] == "D+"
    assert p["side_b"]["trade_grade"] == "B+"


def test_recovers_trade_details_includes_grades():
    raw = '{"trade_details": {"team_a_gain": 500, "team_b_gain": -500}}'
    p = parse_llm_response(raw)
    assert p["side_a"]["trade_grade"] in {"A-", "B+", "B", "C+", "C"}
    assert p["side_b"]["trade_grade"] in {"D+", "D", "D-", "C-", "C"}


def test_hoists_pros_cons_from_nested_ktc_delta():
    raw = (
        '{"winner":"even","summary_bullets":["x"],'
        '"side_a":{"ktc_delta":{"values_in":100,"values_out":80,"net":20,'
        '"pros":["Pick timing fits rebuild"],"cons":["QB depth cost"],'
        '"per_asset":[]}},"side_b":{"ktc_delta":{"values_in":80,"values_out":100,'
        '"net":-20,"pros":["Adds starter"],"cons":["Sends pick"],"per_asset":[]}}}'
    )
    p = parse_llm_response(raw)
    assert p["side_a"]["pros"] == ["Pick timing fits rebuild"]
    assert p["side_a"]["cons"] == ["QB depth cost"]
    assert p["side_b"]["pros"] == ["Adds starter"]


def test_unwraps_grades_object():
    raw = (
        '{"winner":"side_a","summary_bullets":["x"],'
        '"side_a":{"grades":{"trade_grade":"B+","pros":["Win"],"cons":["Risk"],'
        '"ktc_delta":{"values_in":10,"values_out":5,"net":5,"per_asset":[]}}},'
        '"side_b":{}}'
    )
    p = parse_llm_response(raw)
    assert p["side_a"]["trade_grade"] == "B+"
    assert p["side_a"]["pros"] == ["Win"]
    assert p["side_a"]["ktc_delta"]["net"] == 5


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
