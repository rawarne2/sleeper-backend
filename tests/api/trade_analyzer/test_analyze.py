"""POST /api/trade-analyzer/analyze."""

_BASE = {
    "league_id": "1210364682523656192",
    "season": "2026",
    "side_a": {"roster_id": 3, "player_ids": ["4881"], "pick_ids": []},
    "side_b": {"roster_id": 7, "player_ids": ["4017"], "pick_ids": []},
    "provider": "echo",
}


def test_analyze_happy_path_with_echo(client):
    resp = client.post("/api/trade-analyzer/analyze", json=_BASE)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["winner"] in ("side_a", "side_b", "even")
    assert 0 <= body["fairness_score"] <= 100
    assert body["provider_used"] == "echo"
    assert body["elapsed_ms"] >= 0


def test_analyze_400_on_bad_request(client):
    body = {**_BASE}
    body.pop("league_id")
    resp = client.post("/api/trade-analyzer/analyze", json=body)
    assert resp.status_code == 400


def test_analyze_503_when_disabled(client, monkeypatch):
    monkeypatch.setenv("TRADE_ANALYZER_ENABLED", "false")
    resp = client.post("/api/trade-analyzer/analyze", json=_BASE)
    assert resp.status_code == 503


def test_analyze_503_when_unknown_provider(client):
    body = {**_BASE, "provider": "does-not-exist"}
    resp = client.post("/api/trade-analyzer/analyze", json=body)
    assert resp.status_code == 503


def test_analyze_429_when_rate_limited(client, monkeypatch):
    monkeypatch.setenv("TRADE_ANALYZER_RATE_LIMIT_PER_HOUR", "1")
    monkeypatch.setenv("TRADE_ANALYZER_RATE_LIMIT_KEY", "ip")
    r1 = client.post("/api/trade-analyzer/analyze", json=_BASE)
    assert r1.status_code == 200
    r2 = client.post("/api/trade-analyzer/analyze", json=_BASE)
    assert r2.status_code == 429
    body = r2.get_json()
    assert "retry_after_seconds" in body
