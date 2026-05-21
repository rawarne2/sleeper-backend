"""Request validation tests."""
import pytest

from routes.trade_analyzer.request_schema import (
    RequestValidationError,
    parse_trade_request,
)


_VALID = {
    "league_id": "1210364682523656192",
    "season": "2026",
    "ktc": {"league_format": "superflex", "is_redraft": False, "tep_level": "tep"},
    "side_a": {"roster_id": 3, "player_ids": ["4881"], "pick_ids": []},
    "side_b": {"roster_id": 7, "player_ids": [], "pick_ids": ["2026-r1-mid"]},
}


def test_parses_valid_request():
    req = parse_trade_request(_VALID)
    assert req["league_id"] == "1210364682523656192"
    assert req["side_a"]["roster_id"] == 3


def test_defaults_ktc_when_missing():
    body = {**_VALID}
    body.pop("ktc")
    req = parse_trade_request(body)
    assert req["ktc"] == {
        "league_format": "superflex",
        "is_redraft": False,
        "tep_level": "tep",
    }


def test_rejects_missing_league_id():
    body = {**_VALID}
    body.pop("league_id")
    with pytest.raises(RequestValidationError, match="league_id"):
        parse_trade_request(body)


def test_rejects_missing_season():
    body = {**_VALID}
    body.pop("season")
    with pytest.raises(RequestValidationError, match="season"):
        parse_trade_request(body)


def test_rejects_invalid_season_format():
    body = {**_VALID, "season": "26"}
    with pytest.raises(RequestValidationError, match="season"):
        parse_trade_request(body)


def test_rejects_both_sides_empty():
    body = {**_VALID,
            "side_a": {"roster_id": 1, "player_ids": [], "pick_ids": []},
            "side_b": {"roster_id": 2, "player_ids": [], "pick_ids": []}}
    with pytest.raises(RequestValidationError, match="at least one asset"):
        parse_trade_request(body)


def test_rejects_invalid_league_format():
    body = {**_VALID, "ktc": {"league_format": "PPR",
                              "is_redraft": False, "tep_level": ""}}
    with pytest.raises(RequestValidationError, match="league_format"):
        parse_trade_request(body)


def test_rejects_invalid_tep_level():
    body = {**_VALID, "ktc": {"league_format": "superflex",
                              "is_redraft": False, "tep_level": "xxx"}}
    with pytest.raises(RequestValidationError, match="tep_level"):
        parse_trade_request(body)


def test_rejects_missing_roster_id():
    body = {**_VALID, "side_a": {"player_ids": ["4881"], "pick_ids": []}}
    with pytest.raises(RequestValidationError, match="roster_id"):
        parse_trade_request(body)


def test_optional_fields_normalized():
    req = parse_trade_request(_VALID)
    assert req["additional_context"] is None
    assert req["provider"] is None
    assert req["model"] is None


def test_rejects_invalid_pick_id_pattern():
    body = {
        **_VALID,
        "side_a": {"roster_id": 3, "player_ids": ["4881"], "pick_ids": []},
        "side_b": {"roster_id": 7, "player_ids": [], "pick_ids": ["bogus-pick-id"]},
    }
    with pytest.raises(RequestValidationError, match="invalid pick_id"):
        parse_trade_request(body)


def test_normalizes_provider_case():
    body = {**_VALID, "provider": "ECHO"}
    req = parse_trade_request(body)
    assert req["provider"] == "echo"


def test_rejects_unknown_provider():
    body = {**_VALID, "provider": "not_registered"}
    with pytest.raises(RequestValidationError, match="Unknown provider"):
        parse_trade_request(body)


def test_is_tanking_defaults_false():
    req = parse_trade_request(_VALID)
    assert req["side_a"]["is_tanking"] is False
    assert req["side_b"]["is_tanking"] is False


def test_is_tanking_parsed_when_set():
    body = {
        **_VALID,
        "side_a": {**_VALID["side_a"], "is_tanking": True},
        "side_b": {**_VALID["side_b"], "is_tanking": False},
    }
    req = parse_trade_request(body)
    assert req["side_a"]["is_tanking"] is True
    assert req["side_b"]["is_tanking"] is False


def test_rejects_non_bool_is_tanking():
    body = {**_VALID, "side_a": {**_VALID["side_a"], "is_tanking": "yes"}}
    with pytest.raises(RequestValidationError, match="is_tanking"):
        parse_trade_request(body)
