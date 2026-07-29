# tests/unit/valuations/test_tank01_source.py
from unittest.mock import patch

import pytest

from services.valuations.base import SourceUnavailable
from services.valuations.sources.tank01 import Tank01Source


def test_health_without_key():
    with patch("scrapers.tank01_client.is_configured", return_value=False):
        ok, detail = Tank01Source().health()
    assert ok is False
    assert "RAPIDAPI_KEY" in detail


def test_fetch_without_key_raises():
    with patch("scrapers.tank01_client.is_configured", return_value=False):
        with pytest.raises(SourceUnavailable):
            Tank01Source().fetch(season="2026", league_format="superflex",
                                 league_settings={"current_week": 1})


def test_fetch_parses_projection_points():
    projections = {
        "5": {"fantasyPointsDefault": {"standard": 15.0, "halfPPR": 18.0, "PPR": 20.5},
              "longName": "Josh Allen", "pos": "QB", "team": "BUF"},
        "6": {"fantasyPoints": "9.9", "longName": "Backup Guy", "pos": "RB", "team": "NYJ"},
        "7": {"pos": "WR"},  # no points -> skipped
    }
    with patch("scrapers.tank01_client.is_configured", return_value=True), \
         patch("scrapers.tank01_client.sleeper_id_by_tank_id", return_value={"5": "4984"}), \
         patch("scrapers.tank01_client.get_projections", return_value=projections):
        rows = Tank01Source().fetch(season="2026", league_format="superflex",
                                    league_settings={"current_week": 3})

    by_id = {r.external_id: r for r in rows}
    assert set(by_id) == {"5", "6"}
    assert by_id["5"].metric_key == "tank_proj_week"
    assert by_id["5"].metric_value == 20.5          # prefers PPR
    assert by_id["5"].sleeper_id == "4984"          # resolved via id map
    assert by_id["6"].metric_value == 9.9           # falls back to fantasyPoints
