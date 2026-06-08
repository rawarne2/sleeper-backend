from flask import request, jsonify
from routes.helpers import json_api_error
from services.trade_analyzer.feedback_store import load_stashed, save_feedback
from . import trade_analyzer_bp

_VALID_AGREE = {"agree", "disagree", "unsure", "skipped"}


@trade_analyzer_bp.route("/feedback", methods=["POST"])
def submit_feedback():
    body = request.get_json(silent=True) or {}
    analysis_id = body.get("analysis_id")
    client_id = body.get("client_id")
    if not analysis_id or not client_id:
        return json_api_error("analysis_id and client_id are required", 400)

    if body.get("skipped"):
        agree_winner, grade, note = "skipped", None, None
    else:
        agree_winner = body.get("agree_winner")
        if agree_winner not in _VALID_AGREE or agree_winner == "skipped":
            return json_api_error("agree_winner must be agree|disagree|unsure", 400)
        grade = body.get("grade")
        note = body.get("note")

    stash = load_stashed(analysis_id)
    save_feedback(analysis_id=analysis_id, client_id=client_id,
                  league_id=body.get("league_id"), agree_winner=agree_winner,
                  grade=grade, note=note, stash=stash)
    return jsonify({"ok": True, "context_available": stash is not None}), 200
