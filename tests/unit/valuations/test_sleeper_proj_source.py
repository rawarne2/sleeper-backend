# tests/unit/valuations/test_sleeper_proj_source.py
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import requests

from services.valuations.base import SourceUnavailable
from services.valuations.sources.sleeper_proj import SleeperProjectionsSource

SAMPLE = json.loads((Path(__file__).parents[2] / "fixtures" / "sleeper_proj_sample.json").read_text())


def _resp(payload):
    r = MagicMock(status_code=200, json=lambda: payload)
    r.raise_for_status = lambda: None
    return r


def _weekly(by_week):
    """requests.get side effect serving ``by_week[week]`` for /projections/nfl/{season}/{week}."""
    calls = []

    def get(url, params=None, timeout=None):
        week = int(url.rstrip("/").rsplit("/", 1)[1])
        calls.append(week)
        payload = by_week[week]
        if isinstance(payload, Exception):
            raise payload
        return _resp(payload)

    return get, calls


def test_fetch_parses_weekly_projection_points():
    src = SleeperProjectionsSource()
    with patch("services.valuations.sources.sleeper_proj.requests.get") as g:
        g.return_value = _resp(SAMPLE)
        rows = src.fetch(season="2026", league_format="superflex",
                         league_settings={"current_week": 1})
    pts = {(r.external_id, r.metric_key): r.metric_value for r in rows}
    assert pts[("4035", "proj_week")] == 18.5
    # external_id and sleeper_id are both the canonical Sleeper player_id (join key)
    assert rows[0].external_id == "4035"
    assert rows[0].sleeper_id == "4035"
    assert rows[0].source_key == "sleeper_proj"


def test_proj_ros_sums_current_week_through_18():
    by_week = {
        16: [{"player_id": "4035", "stats": {"pts_ppr": 18.5}},
             {"player_id": "6794", "stats": {"pts_ppr": 14.2}}],
        17: [{"player_id": "4035", "stats": {"pts_ppr": 20.0}}],  # 6794 on bye
        18: [{"player_id": "4035", "stats": {"pts_ppr": 10.25}},
             {"player_id": "6794", "stats": {"pts_ppr": 15.0}},
             {"player_id": "9999", "stats": {}}],
    }
    get, calls = _weekly(by_week)
    with patch("services.valuations.sources.sleeper_proj.requests.get", side_effect=get):
        rows = SleeperProjectionsSource().fetch(
            season="2026", league_format="superflex", league_settings={"current_week": 16})

    assert calls == [16, 17, 18]
    vals = {(r.external_id, r.metric_key): r.metric_value for r in rows}
    assert vals[("4035", "proj_week")] == 18.5
    assert vals[("6794", "proj_week")] == 14.2
    assert vals[("4035", "proj_ros")] == 48.75
    assert vals[("6794", "proj_ros")] == 29.2
    assert ("9999", "proj_ros") not in vals
    assert all(r.sleeper_id == r.external_id for r in rows)


def test_week_resolves_from_nfl_state_when_not_in_settings():
    get, calls = _weekly({18: SAMPLE})
    with patch("services.valuations.sources.sleeper_proj.SleeperScraper.fetch_nfl_state",
               return_value={"week": 18, "season_type": "regular"}), \
         patch("services.valuations.sources.sleeper_proj.requests.get", side_effect=get):
        rows = SleeperProjectionsSource().fetch(
            season="2026", league_format="superflex", league_settings={})
    assert calls == [18]
    assert {r.metric_key for r in rows} == {"proj_week", "proj_ros"}


def test_preseason_state_projects_full_season():
    get, calls = _weekly({w: [] for w in range(1, 19)})
    with patch("services.valuations.sources.sleeper_proj.SleeperScraper.fetch_nfl_state",
               return_value={"week": 0, "season_type": "pre"}), \
         patch("services.valuations.sources.sleeper_proj.requests.get", side_effect=get):
        SleeperProjectionsSource().fetch(season="2026", league_format="superflex", league_settings={})
    assert calls == list(range(1, 19))


def test_postseason_emits_nothing():
    with patch("services.valuations.sources.sleeper_proj.SleeperScraper.fetch_nfl_state",
               return_value={"week": 19, "season_type": "post"}), \
         patch("services.valuations.sources.sleeper_proj.requests.get") as g:
        rows = SleeperProjectionsSource().fetch(
            season="2026", league_format="superflex", league_settings={})
    assert rows == []
    g.assert_not_called()


def test_unknown_week_raises_instead_of_defaulting_to_week_one():
    with patch("services.valuations.sources.sleeper_proj.SleeperScraper.fetch_nfl_state",
               return_value=None):
        with pytest.raises(SourceUnavailable):
            SleeperProjectionsSource().fetch(
                season="2026", league_format="superflex", league_settings={})


def test_any_failed_remaining_week_fails_the_source():
    get, _ = _weekly({17: SAMPLE, 18: requests.ConnectionError("boom")})
    with patch("services.valuations.sources.sleeper_proj.requests.get", side_effect=get):
        with pytest.raises(SourceUnavailable):
            SleeperProjectionsSource().fetch(
                season="2026", league_format="superflex", league_settings={"current_week": 17})
