from services.trade_analyzer.output_schema import _SIDE, TRADE_ANALYZER_JSON_SCHEMA


def test_side_no_longer_requires_sleeper_breakdown():
    assert "sleeper_breakdown" not in _SIDE["properties"]
    assert "sleeper_breakdown" not in _SIDE["required"]


def test_summary_bullets_exactly_two():
    sb = TRADE_ANALYZER_JSON_SCHEMA["properties"]["summary_bullets"]
    assert sb.get("minItems") == 2 and sb.get("maxItems") == 2
