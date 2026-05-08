"""compute_owned_picks tests."""
import json
from datetime import datetime, UTC

from managers.sleeper_picks import compute_owned_picks
from models.entities import SleeperLeague, SleeperRoster
from models.extensions import db


def _seed_league(*, status="pre_draft", picks=None, roster_count=12, current_season="2026"):
    settings = {"draft_rounds": 4}
    league = SleeperLeague(
        league_id="L1", name="t", season=current_season,
        roster_positions=json.dumps(["QB", "RB"]),
        scoring_settings=json.dumps({}), league_settings=json.dumps(settings),
        status=status,
        traded_picks=json.dumps(picks or []),
        last_updated=datetime.now(UTC), last_refreshed=datetime.now(UTC),
    )
    db.session.add(league)
    for i in range(1, roster_count + 1):
        db.session.add(SleeperRoster(
            league_id="L1", roster_id=i, owner_id=f"u{i}",
            players=json.dumps([]), starters=json.dumps([]),
            reserve=json.dumps([]), taxi=json.dumps([]),
            roster_metadata=json.dumps({}), settings=json.dumps({"wins": 0, "fpts": 0}),
        ))
    db.session.commit()


def test_pre_draft_seeds_each_roster_with_own_picks(client):
    _seed_league(status="pre_draft", roster_count=12)
    by_roster = compute_owned_picks("L1")
    assert 1 in by_roster
    rounds_for_1 = sorted({(p["season"], p["round"]) for p in by_roster[1]})
    assert ("2026", 1) in rounds_for_1
    assert ("2027", 1) in rounds_for_1


def test_in_season_excludes_current_season(client):
    _seed_league(status="in_season", roster_count=12)
    by_roster = compute_owned_picks("L1")
    seasons = {p["season"] for picks in by_roster.values() for p in picks}
    assert "2026" not in seasons
    assert "2027" in seasons


def test_traded_pick_reassigns_to_current_owner(client):
    _seed_league(status="pre_draft", roster_count=12, picks=[
        {"round": 1, "season": "2026", "roster_id": 1, "owner_id": 5, "previous_owner_id": 8},
    ])
    by_roster = compute_owned_picks("L1")
    one_picks = [(p["season"], p["round"]) for p in by_roster.get(1, [])]
    assert ("2026", 1) not in one_picks
    five_picks = [(p["season"], p["round"]) for p in by_roster[5]]
    assert ("2026", 1) in five_picks


def test_returns_empty_when_league_missing(client):
    assert compute_owned_picks("does-not-exist") == {}


def test_pick_id_canonical_format(client):
    _seed_league(status="pre_draft", roster_count=12)
    by_roster = compute_owned_picks("L1")
    sample = by_roster[1][0]
    assert "-r" in sample["pick_id"]
    assert sample["pick_id"].endswith(("early", "mid", "late")) or "pick" in sample["pick_id"]


def test_slot_buckets_12_team_thirds(client):
    _seed_league(status="pre_draft", roster_count=12)
    rosters = SleeperRoster.query.filter_by(league_id="L1").all()
    for r in rosters:
        s = json.loads(r.settings)
        s["fpts"] = r.roster_id
        r.settings = json.dumps(s)
    db.session.commit()

    by_roster = compute_owned_picks("L1")
    own_pick = next(p for p in by_roster[1] if p["season"] == "2026" and p["round"] == 1)
    assert own_pick["slot_bucket"] == "early"
