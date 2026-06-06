# tests/unit/valuations/test_fantasycalc_source.py
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from services.valuations.sources.fantasycalc import FantasyCalcSource, _num_qbs

SAMPLE = json.loads((Path(__file__).parents[2] / "fixtures" / "fantasycalc_sample.json").read_text())


def test_num_qbs_from_roster_positions():
    assert _num_qbs({"roster_positions": ["QB", "RB", "WR", "SUPER_FLEX"]}) == 2
    assert _num_qbs({"roster_positions": ["QB", "RB", "WR"]}) == 1


def test_fetch_parses_players_and_picks():
    src = FantasyCalcSource()
    with patch("services.valuations.sources.fantasycalc.requests.get") as g:
        g.return_value = MagicMock(status_code=200, json=lambda: SAMPLE)
        g.return_value.raise_for_status = lambda: None
        rows = src.fetch(season="2026", league_format="superflex",
                         league_settings={"roster_positions": ["QB", "SUPER_FLEX"]})
    by_metric = {(r.external_id, r.metric_key): r for r in rows}
    assert by_metric[("1234", "value")].metric_value == 8000
    assert by_metric[("1234", "redraft_value")].metric_value == 9500
    assert by_metric[("1234", "trade_frequency")].metric_value == 0.004
    # FantasyCalc gives the canonical Sleeper id directly -> exact join, no fuzzy matching
    assert by_metric[("1234", "value")].sleeper_id == "4984"
    # pick row present (real FantasyCalc pick-name format)
    assert any(r.external_id == "9001" and r.name == "2026 Pick 1.01" for r in rows)
    # superflex -> numQbs=2 passed to the API
    assert g.call_args.kwargs["params"]["numQbs"] == 2
