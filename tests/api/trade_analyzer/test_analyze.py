"""POST /api/trade-analyzer/analyze."""
from unittest.mock import patch

import pytest


_BASE = {
    "league_id": "1210364682523656192",
    "season": "2026",
    "side_a": {"roster_id": 3, "player_ids": ["4881"], "pick_ids": []},
    "side_b": {"roster_id": 7, "player_ids": ["4034"], "pick_ids": []},
    "provider": "echo",
}


@pytest.fixture
def stubbed_league(league_fixture):
    with patch(
        "services.trade_analyzer.analyzer.load_league_bundle",
        return_value=league_fixture,
    ), patch(
        "routes.trade_analyzer.preview.load_league_bundle",
        return_value=league_fixture,
    ):
        yield


def test_analyze_happy_path_with_echo(client, stubbed_league):
    resp = client.post("/api/trade-analyzer/analyze", json=_BASE)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["winner"] in ("side_a", "side_b", "even")
    assert body["provider_used"] == "echo"
    assert body["elapsed_ms"] >= 0


def test_analyze_400_on_bad_request(client):
    body = {**_BASE}
    body.pop("league_id")
    resp = client.post("/api/trade-analyzer/analyze", json=body)
    assert resp.status_code == 400


def test_analyze_503_when_disabled(client, monkeypatch, stubbed_league):
    monkeypatch.setenv("TRADE_ANALYZER_ENABLED", "false")
    resp = client.post("/api/trade-analyzer/analyze", json=_BASE)
    assert resp.status_code == 503


def test_analyze_400_when_unknown_provider(client, stubbed_league):
    body = {**_BASE, "provider": "does-not-exist"}
    resp = client.post("/api/trade-analyzer/analyze", json=body)
    assert resp.status_code == 400
    assert "Unknown provider" in (resp.get_json() or {}).get("error", "")


def test_analyze_400_when_echo_in_vercel_production(client, monkeypatch, stubbed_league):
    monkeypatch.delenv("TRADE_ANALYZER_PRODUCTION_LOCK", raising=False)
    monkeypatch.setenv("VERCEL_ENV", "production")
    resp = client.post("/api/trade-analyzer/analyze", json=_BASE)
    assert resp.status_code == 400
    err = (resp.get_json() or {}).get("error", "")
    assert "Gemini" in err


def test_analyze_accepts_explicit_gemini_in_vercel_production(
    client, monkeypatch, stubbed_league,
):
    monkeypatch.delenv("TRADE_ANALYZER_PRODUCTION_LOCK", raising=False)
    monkeypatch.setenv("VERCEL_ENV", "production")
    body = {**_BASE, "provider": "gemini"}
    with patch("cache.rate_limiter.get_redis_client", return_value=None), patch(
        "routes.trade_analyzer.analyze.run_analysis"
    ) as run:
        from services.trade_analyzer.analyzer import AnalyzerOutcome

        run.return_value = AnalyzerOutcome(status_code=200, body={
            "winner": "even", "summary_bullets": [],
            "side_a": {}, "side_b": {},
        })
        resp = client.post("/api/trade-analyzer/analyze", json=body)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    run.assert_called_once()


def test_analyze_404_when_league_missing(client):
    # No stubbed_league → real loader runs against empty DB → 404.
    resp = client.post("/api/trade-analyzer/analyze", json=_BASE)
    assert resp.status_code == 404


def test_analyze_429_when_rate_limited(client, monkeypatch, stubbed_league):
    monkeypatch.setenv("TRADE_ANALYZER_RATE_LIMIT_PER_HOUR", "1")
    monkeypatch.setenv("TRADE_ANALYZER_RATE_LIMIT_KEY", "ip")
    r1 = client.post("/api/trade-analyzer/analyze", json=_BASE)
    assert r1.status_code == 200
    r2 = client.post("/api/trade-analyzer/analyze", json=_BASE)
    assert r2.status_code == 429


def test_analyze_returns_analysis_id(client, stubbed_league):
    resp = client.post("/api/trade-analyzer/analyze", json=_BASE)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert isinstance(body.get("analysis_id"), str) and len(body["analysis_id"]) >= 8
