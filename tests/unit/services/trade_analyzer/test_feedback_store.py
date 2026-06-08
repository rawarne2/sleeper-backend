from models.entities import TradeFeedback
from models.extensions import db
from services.trade_analyzer.feedback_store import save_feedback


def test_save_with_stash_writes_full_row(app_context):
    stash = {"request": {"a": 1}, "context": {"c": 2}, "response": {"winner": "side_a"},
             "provider": "gemini", "model": "flash", "league_id": "L9",
             "created_at": "2026-06-08T00:00:00Z"}
    save_feedback(analysis_id="id1", client_id="c1", league_id="L9",
                  agree_winner="agree", grade="A", note=None, stash=stash)
    row = TradeFeedback.query.get("id1")
    assert row.provider == "gemini" and row.context_available is True
    assert row.response_json and row.league_id == "L9"


def test_save_without_stash_writes_degraded_row(app_context):
    save_feedback(analysis_id="id2", client_id="c1", league_id="L9",
                  agree_winner="skipped", grade=None, note=None, stash=None)
    row = TradeFeedback.query.get("id2")
    assert row.context_available is False
    assert row.context_json is None and row.agree_winner == "skipped"
    assert row.league_id == "L9"  # from body, since no stash
