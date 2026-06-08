from datetime import datetime, UTC
from models.entities import TradeFeedback
from models.extensions import db


def test_trade_feedback_roundtrip(app_context):
    fb = TradeFeedback(
        id="abc-123", client_id="c1", league_id="L1", provider="echo", model="echo",
        request_json="{}", context_json="{}", response_json="{}",
        agree_winner="agree", user_grade="B", note="ok",
        context_available=True, created_at=datetime.now(UTC), feedback_at=datetime.now(UTC),
    )
    db.session.add(fb); db.session.commit()
    got = TradeFeedback.query.get("abc-123")
    assert got.agree_winner == "agree" and got.user_grade == "B"
    assert got.context_available is True
