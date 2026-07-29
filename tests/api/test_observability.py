"""Request-id and timing middleware behavior."""


def test_request_id_and_timing_headers(client):
    r = client.get("/api/ktc/health")
    assert len(r.headers["x-request-id"]) == 32  # uuid4().hex
    float(r.headers["x-response-time-ms"])


def test_incoming_request_id_is_echoed(client):
    r = client.get("/api/ktc/health", headers={"X-Request-ID": "abc-123"})
    assert r.headers["x-request-id"] == "abc-123"


def test_init_sentry_is_noop_without_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    from web.observability import init_sentry
    assert init_sentry() is False
