"""Tests for the native FastAPI maintenance routes."""


from unittest.mock import MagicMock


def test_maintenance_health_ok(client):
    resp = client.get("/api/maintenance/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_nightly_sync_requires_auth_get(client, monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    resp = client.get("/api/maintenance/nightly-sync")
    assert resp.status_code == 401
    assert resp.json()["status"] == "error"


def test_nightly_sync_requires_auth_post(client, monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    resp = client.post("/api/maintenance/nightly-sync")
    assert resp.status_code == 401
    assert resp.json()["status"] == "error"


def test_nightly_sync_401_has_hint(client, monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    resp = client.post("/api/maintenance/nightly-sync")
    assert resp.status_code == 401
    body = resp.json()
    assert "hint" in body
    assert "CRON_SECRET" in body["hint"]


def test_prewarm_requires_auth(client, monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    resp = client.get("/api/maintenance/prewarm")
    assert resp.status_code == 401
    assert resp.json()["status"] == "error"


def test_prewarm_401_has_no_hint(client, monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    resp = client.get("/api/maintenance/prewarm")
    assert resp.status_code == 401
    body = resp.json()
    # prewarm raises ApiError("Unauthorized", 401) with NO hint kwarg
    assert "hint" not in body


AUTH = {"Authorization": "Bearer test-cron-secret"}
DAILY_FLAGS = ("skip_ktc", "skip_leagues", "skip_research", "skip_weekly_stats",
               "skip_nfl_stats", "skip_injuries", "skip_news")


def _patched_pipeline(monkeypatch):
    """Stub every nightly side effect; return the ordered call log."""
    import routes.maintenance as m

    monkeypatch.setenv("CRON_SECRET", "test-cron-secret")
    calls = []
    daily = MagicMock(side_effect=lambda **kw: calls.append(("daily", kw)) or {"errors": []})
    monkeypatch.setattr(m, "run_daily_refresh", daily)
    monkeypatch.setattr(m, "invalidate_rankings_cache", lambda: calls.append(("invalidate", None)))
    monkeypatch.setattr(m, "_ingest_valuations",
                        lambda: calls.append(("valuations", None)) or {"superflex": {}})
    monkeypatch.setattr(m, "_prewarm_dashboard_caches",
                        lambda app: calls.append(("prewarm", None)) or {"results": [], "failed": 0, "total": 0})
    return calls


def test_nightly_sync_get_runs_every_step_with_valuations_before_prewarm(client, monkeypatch):
    calls = _patched_pipeline(monkeypatch)
    resp = client.get("/api/maintenance/nightly-sync", headers=AUTH)
    assert resp.status_code == 200, resp.text
    assert [c[0] for c in calls] == ["daily", "invalidate", "valuations", "prewarm"]
    assert not any(calls[0][1][flag] for flag in DAILY_FLAGS)
    summary = resp.json()["summary"]
    assert summary["steps"] == ["ktc", "leagues", "research", "weekly_stats", "nfl_stats",
                                "injuries", "news", "valuations", "prewarm"]
    assert "valuations" in summary and "prewarm" in summary


def test_nightly_sync_single_daily_step(client, monkeypatch):
    calls = _patched_pipeline(monkeypatch)
    resp = client.post("/api/maintenance/nightly-sync", headers=AUTH, json={"steps": ["research"]})
    assert resp.status_code == 200, resp.text
    assert [c[0] for c in calls] == ["daily"]
    flags = calls[0][1]
    assert flags["skip_research"] is False
    assert all(flags[f] for f in DAILY_FLAGS if f != "skip_research")


def test_nightly_sync_ktc_step_invalidates_rankings_cache(client, monkeypatch):
    calls = _patched_pipeline(monkeypatch)
    resp = client.post("/api/maintenance/nightly-sync", headers=AUTH, json={"steps": ["ktc"]})
    assert resp.status_code == 200, resp.text
    assert [c[0] for c in calls] == ["daily", "invalidate"]


def test_nightly_sync_valuations_only_skips_daily_refresh(client, monkeypatch):
    calls = _patched_pipeline(monkeypatch)
    resp = client.post("/api/maintenance/nightly-sync", headers=AUTH, json={"steps": ["valuations"]})
    assert resp.status_code == 200, resp.text
    assert [c[0] for c in calls] == ["valuations"]
    assert resp.json()["summary"]["steps"] == ["valuations"]


def test_nightly_sync_rejects_unknown_step(client, monkeypatch):
    _patched_pipeline(monkeypatch)
    resp = client.post("/api/maintenance/nightly-sync", headers=AUTH, json={"steps": ["bogus"]})
    assert resp.status_code == 400


def test_nightly_sync_legacy_skip_flags_still_apply(client, monkeypatch):
    calls = _patched_pipeline(monkeypatch)
    resp = client.post("/api/maintenance/nightly-sync", headers=AUTH,
                       json={"skip_ktc": True, "skip_prewarm": True})
    assert resp.status_code == 200, resp.text
    assert [c[0] for c in calls] == ["daily", "valuations"]
    assert calls[0][1]["skip_ktc"] is True


def test_fc_teams_ppr_defaults_without_leagues(app_context):
    import routes.maintenance as m
    assert sorted(m._fc_teams_ppr()) == [(10, 1.0), (12, 0.5), (12, 1.0)]


def test_fc_teams_ppr_from_persisted_leagues(app_context):
    import json
    from datetime import datetime, UTC
    import routes.maintenance as m
    from models.entities import SleeperLeague, SleeperRoster
    from models.extensions import db

    now = datetime.now(UTC)
    for lid, teams, scoring in (("L1", 10, {"rec": 1.0}), ("L2", 12, {}), ("L3", 12, {"rec": 0.5})):
        db.session.add(SleeperLeague(league_id=lid, season="2026",
                                     scoring_settings=json.dumps(scoring), last_updated=now))
        for rid in range(1, teams + 1):
            db.session.add(SleeperRoster(league_id=lid, roster_id=rid))
    db.session.commit()

    assert m._fc_teams_ppr() == [(10, 1.0), (12, 0.5)]



def test_nightly_prewarm_uses_active_app_and_reports_partial_failure(client, monkeypatch):
    import routes.maintenance as m
    monkeypatch.setenv("CRON_SECRET", "test-cron-secret")
    prewarm = MagicMock(return_value={"failed": 1, "total": 2, "results": []})
    monkeypatch.setattr(m, "_prewarm_dashboard_caches", prewarm)
    response = client.post("/api/maintenance/nightly-sync", headers=AUTH,
                           json={"steps": ["prewarm"]})
    prewarm.assert_called_once_with(client.app)
    assert response.json()["summary"]["errors"][0]["step"] == "prewarm"
