# tests/unit/valuations/test_sleeper_proj_source.py
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from services.valuations.sources.sleeper_proj import SleeperProjectionsSource

SAMPLE = json.loads((Path(__file__).parents[2] / "fixtures" / "sleeper_proj_sample.json").read_text())


def test_fetch_parses_weekly_projection_points():
    src = SleeperProjectionsSource()
    with patch("services.valuations.sources.sleeper_proj.requests.get") as g:
        g.return_value = MagicMock(status_code=200, json=lambda: SAMPLE)
        g.return_value.raise_for_status = lambda: None
        rows = src.fetch(season="2026", league_format="superflex",
                         league_settings={"current_week": 1})
    pts = {(r.external_id, r.metric_key): r.metric_value for r in rows}
    assert pts[("4035", "proj_week")] == 18.5
    # external_id and sleeper_id are both the canonical Sleeper player_id (join key)
    assert rows[0].external_id == "4035"
    assert rows[0].sleeper_id == "4035"
    assert rows[0].source_key == "sleeper_proj"
