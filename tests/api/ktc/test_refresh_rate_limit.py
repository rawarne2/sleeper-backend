"""The expensive KTC refresh endpoints are rate limited (429 when over budget)."""
import routes.ktc.rankings as ktc_rankings_route
import services.ktc_refresh_async as ktc_refresh_async


def _stub_pipeline(monkeypatch):
    """Make the sync refresh path return instantly without scraping or a DB."""
    stub = lambda *a, **k: ktc_refresh_async.KTCRefreshOutcome(
        True, 200, {"operations_summary": {"players_count": 0,
                                           "database_saved_count": 0,
                                           "file_saved": False,
                                           "s3_uploaded": False}})
    # Patch the name the route actually calls (imported into its namespace),
    # and the source module so other callers in the test also see the stub.
    monkeypatch.setattr(ktc_rankings_route, "execute_ktc_refresh_pipeline", stub)
    monkeypatch.setattr(ktc_refresh_async, "execute_ktc_refresh_pipeline", stub)
    monkeypatch.setattr(
        ktc_refresh_async.DatabaseManager, "verify_database_connection",
        staticmethod(lambda: True),
    )


def test_refresh_rate_limited_returns_429(client, monkeypatch):
    # limit=1 in a unique window so this test gets a fresh limiter bucket,
    # isolated from the default-limit instance other tests share.
    monkeypatch.setenv("KTC_REFRESH_RATE_LIMIT_PER_WINDOW", "1")
    monkeypatch.setenv("KTC_REFRESH_RATE_LIMIT_WINDOW_SECONDS", "77")
    _stub_pipeline(monkeypatch)

    first = client.post("/api/ktc/refresh?league_format=1qb&sync=1")
    assert first.status_code == 200

    second = client.post("/api/ktc/refresh?league_format=1qb&sync=1")
    assert second.status_code == 429
    body = second.json()
    assert body["error"] == "Rate limit exceeded"
    assert body.get("retry_after_seconds", 0) >= 1


def test_refresh_rate_limit_can_be_disabled(client, monkeypatch):
    monkeypatch.setenv("KTC_REFRESH_RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("KTC_REFRESH_RATE_LIMIT_PER_WINDOW", "1")
    monkeypatch.setenv("KTC_REFRESH_RATE_LIMIT_WINDOW_SECONDS", "88")
    _stub_pipeline(monkeypatch)

    for _ in range(3):
        r = client.post("/api/ktc/refresh?league_format=1qb&sync=1")
        assert r.status_code == 200
