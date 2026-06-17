"""Bundle season points are computed by the Sleeper scoring engine.

Seeds a TE with one NflPlayerWeekStats row and a league whose scoring
settings reproduce Sleeper's matchup players_points exactly (Kyle Pitts
2025 Wk1 = 12.9 in a 0.5 PPR / 0.5 TEP league).
"""
from __future__ import annotations

import json
from datetime import datetime, UTC

import pytest

from models.entities import (
    NflPlayerWeekStats,
    Player,
    PlayerKTCSuperflexValues,
    SleeperLeague,
    SleeperRoster,
)
from models.extensions import db


def _find_player(body: dict, sleeper_pid: str) -> dict | None:
    players = body.get("data", {}).get("players", [])
    for p in players:
        if p.get("sleeper_player_id") == sleeper_pid:
            return p
    return None


@pytest.fixture
def seeded_pitts_bundle(client):
    """Seed a league, a TE player, a KTC row, a roster, and a weekly stat line."""
    league_id = "1210364682523656192"
    te_pid = "7553"
    scoring = {"rec_yd": 0.1, "rec": 0.5, "bonus_rec_te": 0.5, "rec_td": 6.0}

    p = Player(
        player_name="Kyle Pitts",
        position="TE",
        team="ATL",
        match_key="kylepitts-TE",
        sleeper_player_id=te_pid,
        last_updated=datetime.now(UTC),
    )
    db.session.add(p)
    db.session.flush()
    db.session.add(
        PlayerKTCSuperflexValues(player_id=p.id, is_redraft=False, value=5000, rank=40)
    )

    league = SleeperLeague(
        league_id=league_id,
        name="Salt Factory",
        season="2025",
        status="in_season",
        scoring_settings=json.dumps(scoring),
        roster_positions=json.dumps(["QB", "RB", "WR", "TE", "FLEX", "SUPER_FLEX"]),
        last_updated=datetime.now(UTC),
    )
    db.session.add(league)
    db.session.flush()
    db.session.add(
        SleeperRoster(
            league_id=league_id,
            roster_id=1,
            owner_id="u1",
            players=json.dumps([te_pid]),
            starters=json.dumps([te_pid]),
        )
    )

    db.session.add(
        NflPlayerWeekStats(
            season="2025",
            week=1,
            player_id=te_pid,
            stats={"rec_yd": 59.0, "rec": 7.0, "bonus_rec_te": 7.0, "gp": 1.0},
            last_updated=datetime.now(UTC),
        )
    )
    db.session.commit()
    return {"league_id": league_id, "te_pid": te_pid}


def test_bundle_points_reproduce_sleeper(client, seeded_pitts_bundle):
    res = client.get(
        f"/api/dashboard/league/{seeded_pitts_bundle['league_id']}"
        "?season=2025&league_format=superflex&is_redraft=false&tep_level=tep"
    )
    assert res.status_code == 200
    body = res.get_json()
    te = _find_player(body, seeded_pitts_bundle["te_pid"])
    assert te is not None
    assert te["stats"]["total_points"] == 12.9
    assert te["stats"]["average_points"] == 12.9
    assert te["stats"]["games_played"] == 1
