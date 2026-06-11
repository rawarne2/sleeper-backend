# tests/api/players/test_players_all.py
"""Tests for GET /api/players/all."""
from datetime import datetime, UTC

import pytest

from models.entities import Player, PlayerKTCSuperflexValues, PlayerKTCOneQBValues, ValueSnapshot
from models.extensions import db


def _seed_player(name, position, sleeper_id, match_key):
    p = Player(
        player_name=name,
        position=position,
        team="TST",
        sleeper_player_id=sleeper_id,
        match_key=match_key,
        last_updated=datetime.now(UTC),
    )
    db.session.add(p)
    db.session.flush()
    return p


def _seed_superflex_values(player_id, value, rank, is_redraft=False):
    db.session.add(PlayerKTCSuperflexValues(
        player_id=player_id, is_redraft=is_redraft, value=value, rank=rank,
    ))


def _seed_oneqb_values(player_id, value, rank, is_redraft=False):
    db.session.add(PlayerKTCOneQBValues(
        player_id=player_id, is_redraft=is_redraft, value=value, rank=rank,
    ))


def _seed_value_snapshot(player_id, source_key, league_format, value, rank):
    db.session.add(ValueSnapshot(
        player_id=player_id,
        source_key=source_key,
        league_format=league_format,
        metric_key="value",
        metric_value=float(value),
        rank=rank,
        as_of=datetime.now(UTC),
    ))


class TestPlayersAll:
    """Tests for GET /api/players/all."""

    def test_returns_200_with_players_list(self, client):
        """Endpoint returns 200 with a players list, no league_id required."""
        p = _seed_player("Patrick Mahomes", "QB", "4046", "patrickmahomes-QB")
        _seed_superflex_values(p.id, 9500, 1)
        _seed_value_snapshot(p.id, "ktc", "superflex", 9500, 1)
        db.session.commit()

        resp = client.get("/api/players/all?league_format=superflex")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert isinstance(data["players"], list)
        assert len(data["players"]) > 0

    def test_response_envelope_fields(self, client):
        """Response includes all required envelope fields."""
        p = _seed_player("Justin Jefferson", "WR", "6794", "justinjefferson-WR")
        _seed_superflex_values(p.id, 8500, 2)
        db.session.commit()

        resp = client.get("/api/players/all?league_format=superflex")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "status" in data
        assert "timestamp" in data
        assert "league_format" in data
        assert "is_redraft" in data
        assert "tep_level" in data
        assert "count" in data
        assert "players" in data
        assert data["league_format"] == "superflex"
        assert data["is_redraft"] is False
        assert data["tep_level"] == ""
        assert data["count"] == len(data["players"])

    def test_player_has_unified_dashboard_shape(self, client):
        """Each player has the unified dashboard shape: sleeper_player_id, playerName, position, ktc, values."""
        p = _seed_player("Tyreek Hill", "WR", "4984", "tyreekhill-WR")
        _seed_superflex_values(p.id, 7500, 3)
        _seed_value_snapshot(p.id, "ktc", "superflex", 7500, 3)
        _seed_value_snapshot(p.id, "fantasycalc", "superflex", 7200, 4)
        db.session.commit()

        resp = client.get("/api/players/all?league_format=superflex")
        assert resp.status_code == 200
        players = resp.get_json()["players"]
        assert len(players) > 0

        player = next((pl for pl in players if pl.get("sleeper_player_id") == "4984"), None)
        assert player is not None, "Seeded player should be in the response"
        assert "sleeper_player_id" in player
        assert "playerName" in player
        assert "position" in player
        assert "ktc" in player
        assert "values" in player

    def test_player_values_block_has_blended_and_sources(self, client):
        """Each player's values block has blended and sources with ktc/fantasycalc."""
        p = _seed_player("CeeDee Lamb", "WR", "6845", "ceeDee-WR")
        _seed_superflex_values(p.id, 8200, 2)
        _seed_value_snapshot(p.id, "ktc", "superflex", 8200, 2)
        _seed_value_snapshot(p.id, "fantasycalc", "superflex", 7900, 3)
        db.session.commit()

        resp = client.get("/api/players/all?league_format=superflex")
        players = resp.get_json()["players"]
        player = next((pl for pl in players if pl.get("sleeper_player_id") == "6845"), None)
        assert player is not None

        assert player["values"]["blended"] is not None
        assert "ktc" in player["values"]["sources"]
        assert player["values"]["sources"]["ktc"]["value"] == 8200.0
        assert "fantasycalc" in player["values"]["sources"]
        assert player["values"]["sources"]["fantasycalc"]["value"] == 7900.0

    def test_superflex_vs_1qb_selects_correct_values(self, client):
        """league_format=1qb vs superflex returns players with different value sets."""
        p = _seed_player("Lamar Jackson", "QB", "4949", "lamarjackson-QB")
        _seed_superflex_values(p.id, 9000, 1)
        _seed_oneqb_values(p.id, 7000, 5)
        _seed_value_snapshot(p.id, "ktc", "superflex", 9000, 1)
        _seed_value_snapshot(p.id, "ktc", "1qb", 7000, 5)
        db.session.commit()

        resp_sf = client.get("/api/players/all?league_format=superflex")
        players_sf = resp_sf.get_json()["players"]
        p_sf = next((pl for pl in players_sf if pl.get("sleeper_player_id") == "4949"), None)
        assert p_sf is not None
        assert p_sf["ktc"]["superflexValues"] is not None
        assert p_sf["ktc"]["oneQBValues"] is None

        resp_1qb = client.get("/api/players/all?league_format=1qb")
        players_1qb = resp_1qb.get_json()["players"]
        p_1qb = next((pl for pl in players_1qb if pl.get("sleeper_player_id") == "4949"), None)
        assert p_1qb is not None
        assert p_1qb["ktc"]["oneQBValues"] is not None
        assert p_1qb["ktc"]["superflexValues"] is None

    def test_players_without_ktc_values_for_format_are_excluded(self, client):
        """Players lacking a KTC row for the requested format are excluded."""
        p_sf_only = _seed_player("No OneQB Player", "WR", "9991", "nooqb-WR")
        _seed_superflex_values(p_sf_only.id, 5000, 10)
        db.session.commit()

        resp = client.get("/api/players/all?league_format=1qb")
        players = resp.get_json()["players"]
        ids = [pl.get("sleeper_player_id") for pl in players]
        assert "9991" not in ids, "Player with only superflex values should be excluded for 1qb"

    def test_tep_level_honored(self, client):
        """tep_level param is reflected in the envelope and overrides ktc value."""
        p = _seed_player("Sam LaPorta", "TE", "10229", "samlapora-TE")
        ktc_row = PlayerKTCSuperflexValues(
            player_id=None, is_redraft=False,
            value=5000, rank=20,
            tep_value=5500, tep_rank=15,
        )
        db.session.add(p)
        db.session.flush()
        ktc_row.player_id = p.id
        db.session.add(ktc_row)
        db.session.commit()

        resp = client.get("/api/players/all?league_format=superflex&tep_level=tep")
        data = resp.get_json()
        assert data["tep_level"] == "tep"
        players = data["players"]
        te = next((pl for pl in players if pl.get("sleeper_player_id") == "10229"), None)
        assert te is not None
        # When tep_level=tep and tep_value is present, value should be overridden
        assert te["ktc"]["superflexValues"]["value"] == 5500

    def test_is_redraft_honored(self, client):
        """is_redraft=true selects redraft KTC rows."""
        p = _seed_player("Bijan Robinson", "RB", "10228", "bijanrobinson-RB")
        _seed_superflex_values(p.id, 8000, 3, is_redraft=False)
        _seed_superflex_values(p.id, 4000, 8, is_redraft=True)
        db.session.commit()

        resp_dyn = client.get("/api/players/all?league_format=superflex&is_redraft=false")
        p_dyn = next(
            (pl for pl in resp_dyn.get_json()["players"] if pl.get("sleeper_player_id") == "10228"),
            None,
        )
        assert p_dyn is not None
        assert p_dyn["ktc"]["is_redraft"] is False

        resp_rd = client.get("/api/players/all?league_format=superflex&is_redraft=true")
        p_rd = next(
            (pl for pl in resp_rd.get_json()["players"] if pl.get("sleeper_player_id") == "10228"),
            None,
        )
        assert p_rd is not None
        assert p_rd["ktc"]["is_redraft"] is True

    def test_no_league_id_required(self, client):
        """Endpoint is standalone — no league_id needed."""
        p = _seed_player("Ja'Marr Chase", "WR", "6794x", "jamarr-WR")
        _seed_superflex_values(p.id, 8900, 1)
        db.session.commit()

        resp = client.get("/api/players/all")
        assert resp.status_code == 200

    def test_invalid_league_format_returns_400(self, client):
        """Invalid league_format returns 400 error envelope."""
        resp = client.get("/api/players/all?league_format=invalid")
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["status"] == "error"

    def test_invalid_is_redraft_returns_400(self, client):
        """Non-boolean is_redraft returns 400."""
        resp = client.get("/api/players/all?is_redraft=maybe")
        assert resp.status_code == 400

    def test_default_params(self, client):
        """Default params: league_format=superflex, is_redraft=false, tep_level=''."""
        resp = client.get("/api/players/all")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["league_format"] == "superflex"
        assert data["is_redraft"] is False
        assert data["tep_level"] == ""

    def test_count_matches_players_length(self, client):
        """Response count field matches actual length of players list."""
        p1 = _seed_player("Player One", "QB", "99001", "pone-QB")
        _seed_superflex_values(p1.id, 7000, 5)
        p2 = _seed_player("Player Two", "RB", "99002", "ptwo-RB")
        _seed_superflex_values(p2.id, 6000, 10)
        db.session.commit()

        resp = client.get("/api/players/all?league_format=superflex")
        data = resp.get_json()
        assert data["count"] == len(data["players"])

    def test_season_param_accepted(self, client):
        """season param is accepted without error (used for future ownership)."""
        p = _seed_player("Drake London", "WR", "8138", "drakelondon-WR")
        _seed_superflex_values(p.id, 6500, 8)
        db.session.commit()

        resp = client.get("/api/players/all?league_format=superflex&season=2025")
        assert resp.status_code == 200

    def test_invalid_season_format_returns_400(self, client):
        """Non 4-digit season returns 400."""
        resp = client.get("/api/players/all?league_format=superflex&season=25")
        assert resp.status_code == 400
