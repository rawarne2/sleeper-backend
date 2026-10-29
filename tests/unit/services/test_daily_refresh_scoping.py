"""Scheduled nightly-sync scopes scraping to the current season only.

Prior seasons are immutable, so ``run_daily_refresh`` (no explicit league_ids /
seasons) must refresh only current-season leagues and ingest research + NFL week
stats for the current season alone. Operator overrides still reach every season.
"""
from datetime import datetime, UTC
from unittest.mock import patch

import pytest

from models.entities import SleeperLeague
from models.extensions import db
import services.daily_refresh as dr


CURRENT = str(datetime.now(UTC).year)
PRIOR_1 = str(int(CURRENT) - 1)
PRIOR_2 = str(int(CURRENT) - 2)


def _seed_leagues():
    rows = [
        SleeperLeague(league_id="cur_league", season=CURRENT, name="Current"),
        SleeperLeague(league_id="old_league_1", season=PRIOR_1, name="Last year"),
        SleeperLeague(league_id="old_league_2", season=PRIOR_2, name="Two years ago"),
    ]
    db.session.add_all(rows)
    db.session.commit()


def test_current_season_league_ids_filters_to_current(app_context):
    _seed_leagues()
    assert dr._current_season_league_ids(CURRENT) == ["cur_league"]


def test_current_season_league_ids_falls_back_to_example_seed(app_context):
    # Empty DB -> only the example league whose season matches current (if any),
    # otherwise every persisted league. Either way, never a prior-season-only set.
    ids = dr._current_season_league_ids(CURRENT)
    expected = [lid for lid, season in dr.EXAMPLE_LEAGUE_IDS if season == CURRENT]
    if expected:
        assert ids == expected


def test_run_daily_refresh_scopes_scraping_to_current_season(app_context):
    _seed_leagues()

    with patch.object(
        dr, "refresh_leagues",
        return_value={"leagues": {}, "errors": [], "seasons": [CURRENT]},
    ) as m_leagues, patch.object(
        dr, "persist_research", return_value={"status": "success"}
    ) as m_research, patch.object(
        dr, "refresh_weekly_stats_for_leagues",
        return_value={"leagues": [], "errors": []},
    ), patch.object(
        dr, "ingest_nfl_week_stats", return_value={"saved": 0}
    ) as m_nfl, patch.object(
        dr.SleeperScraper, "fetch_nfl_state", return_value={"week": 8, "season_type": "regular"}
    ):
        dr.run_daily_refresh(skip_ktc=True)

    # Only the current-season league is scraped.
    m_leagues.assert_called_once_with(["cur_league"])

    # Research only touches the current season.
    research_seasons = {call.args[0] for call in m_research.call_args_list}
    assert research_seasons == {CURRENT}

    # NFL week stats ingested for the current season only — never a prior season.
    nfl_seasons = {call.args[0] for call in m_nfl.call_args_list}
    assert nfl_seasons == {CURRENT}


def test_explicit_league_ids_override_season_scope(app_context):
    _seed_leagues()

    with patch.object(
        dr, "refresh_leagues",
        return_value={"leagues": {}, "errors": [], "seasons": [PRIOR_1]},
    ) as m_leagues, patch.object(
        dr, "persist_research", return_value={"status": "success"}
    ), patch.object(
        dr, "refresh_weekly_stats_for_leagues",
        return_value={"leagues": [], "errors": []},
    ), patch.object(
        dr, "ingest_nfl_week_stats", return_value={"saved": 0}
    ), patch.object(
        dr.SleeperScraper, "fetch_nfl_state", return_value={"week": 8, "season_type": "regular"}
    ):
        dr.run_daily_refresh(skip_ktc=True, league_ids=["old_league_1"])

    m_leagues.assert_called_once_with(["old_league_1"])


@pytest.mark.parametrize("state, env, expected", [
    ({"week": 8, "season_type": "regular"}, None, 8),
    ({"week": 1, "season_type": "pre"}, None, 1),
    ({"week": 20, "season_type": "post"}, None, 18),
    (None, None, 1),
    ({"week": 8, "season_type": "regular"}, "3", 3),
])
def test_default_research_week_follows_nfl_state(monkeypatch, state, env, expected):
    if env is None:
        monkeypatch.delenv("DAILY_REFRESH_RESEARCH_WEEK", raising=False)
    else:
        monkeypatch.setenv("DAILY_REFRESH_RESEARCH_WEEK", env)
    with patch.object(dr.SleeperScraper, "fetch_nfl_state", return_value=state):
        assert dr._default_research_week() == expected


def test_scheduled_research_uses_current_nfl_week(app_context, monkeypatch):
    monkeypatch.delenv("DAILY_REFRESH_RESEARCH_WEEK", raising=False)
    with patch.object(
        dr, "refresh_leagues", return_value={"leagues": {}, "errors": [], "seasons": [CURRENT]},
    ), patch.object(
        dr, "persist_research", return_value={"status": "success"}
    ) as m_research, patch.object(
        dr, "refresh_weekly_stats_for_leagues", return_value={"leagues": [], "errors": []},
    ), patch.object(
        dr, "ingest_nfl_week_stats", return_value={"saved": 0}
    ), patch.object(
        dr.SleeperScraper, "fetch_nfl_state", return_value={"week": 8, "season_type": "regular"}
    ):
        dr.run_daily_refresh(skip_ktc=True, league_ids=["cur_league"])

    assert {call.kwargs["week"] for call in m_research.call_args_list} == {8}


def _stub_all(stack):
    mocks = {}
    for name, rv in (
        ("refresh_leagues", {"leagues": {}, "errors": [], "seasons": [CURRENT]}),
        ("persist_research", {"status": "success"}),
        ("refresh_weekly_stats_for_leagues", {"leagues": [], "errors": []}),
        ("ingest_nfl_week_stats", {"saved": 0}),
        ("ingest_nflverse_injuries", {"saved": 0}),
        ("ingest_player_news", {"saved": 0}),
    ):
        mocks[name] = stack.enter_context(patch.object(dr, name, return_value=rv))
    stack.enter_context(patch.object(
        dr.SleeperScraper, "fetch_nfl_state", return_value={"week": 8, "season_type": "regular"}))
    return mocks


def test_skip_flags_isolate_each_step(app_context):
    from contextlib import ExitStack
    _seed_leagues()
    with ExitStack() as stack:
        mocks = _stub_all(stack)
        dr.run_daily_refresh(skip_ktc=True, skip_leagues=True, skip_research=True,
                             skip_weekly_stats=True, skip_injuries=True, skip_news=True)
    assert mocks["ingest_nfl_week_stats"].call_args_list[0].args == (CURRENT,)
    for name in ("refresh_leagues", "persist_research", "refresh_weekly_stats_for_leagues",
                 "ingest_nflverse_injuries", "ingest_player_news"):
        mocks[name].assert_not_called()


def test_research_without_leagues_step_defaults_to_current_season(app_context):
    from contextlib import ExitStack
    _seed_leagues()
    with ExitStack() as stack:
        mocks = _stub_all(stack)
        dr.run_daily_refresh(skip_ktc=True, skip_leagues=True, skip_weekly_stats=True,
                             skip_nfl_stats=True, skip_injuries=True, skip_news=True)
    mocks["refresh_leagues"].assert_not_called()
    assert {c.args[0] for c in mocks["persist_research"].call_args_list} == {CURRENT}
