# tests/unit/valuations/test_resolver.py
from services.valuations.resolver import (
    resolve_player_id, build_sleeper_index, build_name_index,
)


def test_resolve_prefers_sleeper_id():
    assert resolve_player_id(sleeper_id="4984", name="Josh Allen", position="QB",
                             sleeper_index={"4984": 42}, name_index={"joshallen-QB": 99}) == 42


def test_resolve_falls_back_to_name_when_no_sleeper_id():
    assert resolve_player_id(sleeper_id=None, name="Josh Allen", position="QB",
                             sleeper_index={}, name_index={"joshallen-QB": 7}) == 7
    # suffix-insensitive via create_player_match_key
    assert resolve_player_id(sleeper_id=None, name="Josh Allen Jr.", position="QB",
                             sleeper_index={}, name_index={"joshallen-QB": 7}) == 7


def test_resolve_none_when_no_match():
    assert resolve_player_id(sleeper_id="x", name="Nobody", position="WR",
                             sleeper_index={}, name_index={}) is None


class _P:
    def __init__(self, id, sid, mk):
        self.id = id
        self.sleeper_player_id = sid
        self.match_key = mk


def test_build_indexes():
    players = [_P(1, "100", "a-QB"), _P(2, None, "b-RB"), _P(3, "300", "c-WR")]
    assert build_sleeper_index(players) == {"100": 1, "300": 3}
    assert build_name_index(players) == {"a-QB": 1, "b-RB": 2, "c-WR": 3}
