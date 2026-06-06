# tests/api/test_valuations_refresh.py
def test_refresh_valuations_returns_summary(client, monkeypatch):
    import routes.valuations as rv
    monkeypatch.setattr(rv, "ingest_valuations",
                        lambda *a, **k: {"fantasycalc": "10 snapshots"})
    resp = client.post("/api/valuations/refresh",
                       json={"league_format": "superflex", "sources": ["fantasycalc"]})
    assert resp.status_code == 200
    assert resp.get_json()["results"]["fantasycalc"] == "10 snapshots"
