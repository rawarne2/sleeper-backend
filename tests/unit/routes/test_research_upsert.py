"""Research upsert must preserve matchup points / starter / roster on the same row."""
from __future__ import annotations

import json
from decimal import Decimal

import pytest

from models.entities import SleeperWeeklyData
from models.extensions import db
from routes.sleeper.research import (
    _upsert_research_rows,
    research_weeks_to_persist,
)


def _seed_points_row(*, season="2026", week=5, lt="dynasty", player_id="4881",
                     points=23.4, roster_id=3, is_starter=True):
    row = SleeperWeeklyData(
        season=season,
        week=week,
        league_type=lt,
        player_id=player_id,
        points=points,
        roster_id=roster_id,
        is_starter=is_starter,
    )
    db.session.add(row)
    db.session.commit()
    return row


def test_upsert_preserves_existing_points_when_research_arrives(app_context):
    _seed_points_row()

    payload = {
        "4881": {"owned": 88.0, "started": 72.5},
        "5500": {"owned": 12.4, "started": 1.2},
    }
    counts = _upsert_research_rows("2026", 5, "dynasty", payload)
    assert counts["inserted"] == 1
    assert counts["updated"] == 1

    josh = SleeperWeeklyData.query.filter_by(
        season="2026", week=5, league_type="dynasty", player_id="4881"
    ).one()
    # Matchup data must survive the research upsert
    assert float(josh.points) == pytest.approx(23.4)
    assert josh.roster_id == 3
    assert josh.is_starter is True
    assert json.loads(josh.research_data) == {"owned": 88.0, "started": 72.5}

    new_row = SleeperWeeklyData.query.filter_by(
        season="2026", week=5, league_type="dynasty", player_id="5500"
    ).one()
    # Inserted rows are research-only; points stays null until matchup sync runs
    assert new_row.points is None
    assert new_row.is_starter in (False, None)
    assert json.loads(new_row.research_data) == {"owned": 12.4, "started": 1.2}


def test_upsert_refreshes_research_for_existing_research_row(app_context):
    db.session.add(SleeperWeeklyData(
        season="2026", week=5, league_type="dynasty", player_id="9999",
        research_data=json.dumps({"owned": 5.0, "started": 0.1}),
    ))
    db.session.commit()

    counts = _upsert_research_rows(
        "2026", 5, "dynasty", {"9999": {"owned": 7.5, "started": 0.4}}
    )
    assert counts["updated"] == 1
    assert counts["inserted"] == 0

    row = SleeperWeeklyData.query.filter_by(player_id="9999").one()
    assert json.loads(row.research_data) == {"owned": 7.5, "started": 0.4}


def test_research_weeks_to_persist_current_season_all_weeks():
    weeks, truncated = research_weeks_to_persist(
        "2026", week_param=None, fetch_all_weeks=True, current_season="2026"
    )
    assert weeks == list(range(1, 19))
    assert truncated is False


def test_research_weeks_to_persist_current_season_single():
    weeks, truncated = research_weeks_to_persist(
        "2026", week_param=4, fetch_all_weeks=False, current_season="2026"
    )
    assert weeks == [4]
    assert truncated is False


def test_research_weeks_to_persist_prior_season_all_truncates_to_18():
    weeks, truncated = research_weeks_to_persist(
        "2024", week_param=None, fetch_all_weeks=True, current_season="2026"
    )
    assert weeks == [18]
    assert truncated is True


def test_research_weeks_to_persist_prior_season_explicit_18():
    weeks, truncated = research_weeks_to_persist(
        "2024", week_param=18, fetch_all_weeks=False, current_season="2026"
    )
    assert weeks == [18]
    assert truncated is False


def test_research_weeks_to_persist_prior_season_other_week_truncates():
    weeks, truncated = research_weeks_to_persist(
        "2024", week_param=7, fetch_all_weeks=False, current_season="2026"
    )
    assert weeks == [18]
    assert truncated is True
