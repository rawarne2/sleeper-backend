import json

from web.errors import ApiError, error_body


def test_error_body_shape():
    body = error_body("bad input", details={"a": 1}, suggestion="try X")
    assert body["status"] == "error"
    assert body["error"] == "bad input"
    assert "timestamp" in body and body["timestamp"].endswith("Z")
    assert body["details"] == json.dumps({"a": 1}, ensure_ascii=False, default=str)
    assert body["suggestion"] == "try X"


def test_api_error_carries_status_and_extra():
    exc = ApiError("nope", 404, details="x", league_id="123")
    assert exc.status_code == 404
    assert exc.extra == {"league_id": "123"}
