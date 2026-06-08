from models.entities import TradeFeedback


def test_feedback_persists_degraded_without_stash(client):
    resp = client.post("/api/trade-analyzer/feedback", json={
        "analysis_id": "fid1", "client_id": "c1", "league_id": "L1",
        "agree_winner": "disagree", "grade": "C", "note": "meh"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    with client.application.app_context():
        row = TradeFeedback.query.get("fid1")
        assert row.agree_winner == "disagree" and row.context_available is False


def test_feedback_skip(client):
    resp = client.post("/api/trade-analyzer/feedback", json={
        "analysis_id": "fid2", "client_id": "c1", "league_id": "L1", "skipped": True})
    assert resp.status_code == 200
    with client.application.app_context():
        assert TradeFeedback.query.get("fid2").agree_winner == "skipped"


def test_feedback_400_on_missing_fields(client):
    resp = client.post("/api/trade-analyzer/feedback", json={"client_id": "c1"})
    assert resp.status_code == 400
