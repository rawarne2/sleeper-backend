"""parse_pick_id + resolve_pick_to_ktc."""
import pytest

from services.trade_analyzer.picks import (
    PickIdError, parse_pick_id, resolve_pick_to_ktc,
)


def test_parse_pick_id_bucket():
    assert parse_pick_id("2026-r1-mid") == {"season": "2026", "round": 1, "slot": "mid"}


def test_parse_pick_id_pickN():
    assert parse_pick_id("2026-r1-pick3") == {"season": "2026", "round": 1, "slot": "pick3"}


def test_parse_pick_id_rejects_garbage():
    for bad in ("2026", "2026-r1", "abcd-r1-mid", "2026-rA-mid", "2026-r1-other"):
        with pytest.raises(PickIdError):
            parse_pick_id(bad)


def test_round_ordinal_ok():
    from services.trade_analyzer.picks import _round_ordinal
    assert _round_ordinal(1) == "1st"
    assert _round_ordinal(2) == "2nd"
    assert _round_ordinal(3) == "3rd"
    assert _round_ordinal(4) == "4th"


def test_resolve_returns_none_when_no_match(client):
    out = resolve_pick_to_ktc("2099-r1-mid", league_format="superflex", tep_level="tep")
    assert out is None
