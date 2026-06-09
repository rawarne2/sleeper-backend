"""POST /api/trade-analyzer/preview."""
from unittest.mock import patch

import pytest


_BASE = {
    "league_id": "1210364682523656192",
    "season": "2026",
    "side_a": {"roster_id": 3, "player_ids": ["4881"], "pick_ids": []},
    "side_b": {"roster_id": 7, "player_ids": ["4034"], "pick_ids": []},
}


@pytest.fixture
def stubbed_league(league_fixture):
    with patch(
        "routes.trade_analyzer.preview.load_league_bundle",
        return_value=league_fixture,
    ):
        yield


def test_preview_returns_context_shape(client, stubbed_league):
    resp = client.post("/api/trade-analyzer/preview", json=_BASE)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    ctx = body["context"]
    assert ctx["league"]["season"] == "2026"
    assert "additional_context" not in ctx
    assert "trade_summary" not in ctx
    assert ctx["trade"]["side_a_incoming"] == ctx["trade"]["side_b_outgoing"]
    assert ctx["trade"]["side_b_incoming"] == ctx["trade"]["side_a_outgoing"]
    assert "consensus_totals" in ctx["trade"]
    assert "ktc_totals" not in ctx["trade"]
    assert body["estimated_tokens"] > 0
    assert body["token_usage"]["prompt_tokens_estimated"] > 0


def test_preview_400_on_missing_field(client, stubbed_league):
    body = {**_BASE}
    body.pop("league_id")
    resp = client.post("/api/trade-analyzer/preview", json=body)
    assert resp.status_code == 400


def test_preview_400_on_both_sides_empty(client, stubbed_league):
    body = {
        **_BASE,
        "side_a": {"roster_id": 1, "player_ids": [], "pick_ids": []},
        "side_b": {"roster_id": 2, "player_ids": [], "pick_ids": []},
    }
    resp = client.post("/api/trade-analyzer/preview", json=body)
    assert resp.status_code == 400


def test_preview_404_when_league_missing(client):
    resp = client.post("/api/trade-analyzer/preview", json=_BASE)
    assert resp.status_code == 404
