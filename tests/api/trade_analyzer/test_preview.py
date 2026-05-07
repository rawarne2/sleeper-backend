"""POST /api/trade-analyzer/preview."""

_BASE = {
    "league_id": "1210364682523656192",
    "season": "2026",
    "side_a": {"roster_id": 3, "player_ids": ["4881"], "pick_ids": []},
    "side_b": {"roster_id": 7, "player_ids": ["4017"], "pick_ids": []},
}


def test_preview_returns_context_shape(client):
    resp = client.post("/api/trade-analyzer/preview", json=_BASE)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert "context" in body
    assert "system_prompt" in body
    assert "user_prompt" in body
    assert body["estimated_tokens"] > 0
    assert body["provider_used"] in ("ollama", "anthropic", "gemini", "groq", "echo")
    assert isinstance(body["model_used"], str)


def test_preview_400_on_missing_field(client):
    body = {**_BASE}
    body.pop("league_id")
    resp = client.post("/api/trade-analyzer/preview", json=body)
    assert resp.status_code == 400
    assert resp.get_json()["status"] == "error"


def test_preview_400_on_both_sides_empty(client):
    body = {
        **_BASE,
        "side_a": {"roster_id": 1, "player_ids": [], "pick_ids": []},
        "side_b": {"roster_id": 2, "player_ids": [], "pick_ids": []},
    }
    resp = client.post("/api/trade-analyzer/preview", json=body)
    assert resp.status_code == 400
