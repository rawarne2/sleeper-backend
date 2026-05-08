"""GET /api/trade-analyzer/providers."""


def test_providers_endpoint_returns_known_providers(client):
    resp = client.get("/api/trade-analyzer/providers")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "default_provider" in body
    assert "providers" in body
    assert body.get("allows_client_provider_model_choice") is True
    names = [p["name"] for p in body["providers"]]
    assert "echo" in names
    assert "gemini" in names
    for entry in body["providers"]:
        assert {"name", "default_model", "available", "detail"} <= set(entry.keys())
    assert body["rate_limit"]["per_hour"] > 0
    assert "enabled" in body


def test_providers_prod_lists_only_anthropic(client, monkeypatch):
    monkeypatch.delenv("TRADE_ANALYZER_ANTHROPIC_ONLY", raising=False)
    monkeypatch.setenv("VERCEL_ENV", "production")
    resp = client.get("/api/trade-analyzer/providers")
    assert resp.status_code == 200
    body = resp.get_json()
    names = [p["name"] for p in body["providers"]]
    assert names == ["anthropic"]
    assert body["allows_client_provider_model_choice"] is False
    assert body["default_provider"] == "anthropic"


def test_providers_endpoint_marks_echo_available(client):
    resp = client.get("/api/trade-analyzer/providers")
    body = resp.get_json()
    echo = next(p for p in body["providers"] if p["name"] == "echo")
    assert echo["available"] is True
