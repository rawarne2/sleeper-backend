import json

from services.trade_analyzer.rag.feedback_doc import feedback_row_to_document

FEEDBACK_FIXTURE = {
    "id": "abc123",
    "agree_winner": "agree",
    "user_grade": "B",
    "note": "Fair win-now move",
    "request_json": json.dumps({
        "season": "2026",
        "ktc": {"league_format": "superflex", "is_redraft": False, "tep_level": ""},
    }),
    "context_json": json.dumps({
        "side_a": {"posture": "contending", "team_needs_signals": {"age_profile": {"contention_window": "now"}}},
        "side_b": {"posture": "tanking", "team_needs_signals": {"age_profile": {"contention_window": "rebuild"}}},
        "trade": {
            "side_a_outgoing": [{"name": "Player A", "position": "WR"}],
            "side_a_incoming": [{"name": "Pick 2027 1st", "position": "PICK"}],
            "side_b_outgoing": [{"name": "Pick 2027 1st", "position": "PICK"}],
            "side_b_incoming": [{"name": "Player A", "position": "WR"}],
        },
    }),
    "response_json": json.dumps({
        "winner": "side_a",
        "side_a": {"trade_grade": "B+", "value_delta": {"net": 400}},
        "side_b": {"trade_grade": "C", "value_delta": {"net": -400}},
    }),
}


def test_feedback_row_to_document_includes_key_fields():
    doc = feedback_row_to_document(FEEDBACK_FIXTURE)
    assert doc["corpus"] == "feedback"
    assert doc["source_id"] == "abc123"
    assert "superflex" in doc["content"]
    assert "agree" in doc["content"]
    assert "Player A" in doc["content"]
