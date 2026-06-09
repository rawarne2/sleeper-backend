from __future__ import annotations
import json
from datetime import datetime, UTC
from typing import Any, Optional
from models.entities import TradeFeedback
from models.extensions import db

_STASH_PREFIX = "trade_analyzer:analysis:v1:"
_STASH_TTL_SECONDS = 7200  # ~2h


def stash_analysis(analysis_id: str, payload: dict[str, Any]) -> None:
    """Best-effort: hold the analysis in Redis so feedback can attach to it. Never raises."""
    try:
        from cache.redis_rankings import get_redis_client
        r = get_redis_client()
        if r:
            r.setex(_STASH_PREFIX + analysis_id, _STASH_TTL_SECONDS,
                    json.dumps(payload).encode("utf-8"))
    except Exception:  # noqa: BLE001 - stashing must never break analysis
        pass


def load_stashed(analysis_id: str) -> Optional[dict[str, Any]]:
    try:
        from cache.redis_rankings import get_redis_client
        r = get_redis_client()
        if not r:
            return None
        raw = r.get(_STASH_PREFIX + analysis_id)
        return json.loads(raw) if raw else None
    except Exception:  # noqa: BLE001
        return None


def _parse_created_at(stash: Optional[dict]) -> datetime:
    if stash and stash.get("created_at"):
        try:
            return datetime.fromisoformat(str(stash["created_at"]).replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(UTC)


def save_feedback(*, analysis_id: str, client_id: str, league_id: Optional[str],
                  agree_winner: str, grade: Optional[str], note: Optional[str],
                  stash: Optional[dict[str, Any]]) -> TradeFeedback:
    now = datetime.now(UTC)
    has = stash is not None
    row = TradeFeedback(
        id=analysis_id, client_id=client_id,
        league_id=(stash.get("league_id") if has else league_id) or league_id,
        provider=(stash.get("provider") if has else None),
        model=(stash.get("model") if has else None),
        request_json=(json.dumps(stash.get("request")) if has else None),
        context_json=(json.dumps(stash.get("context")) if has else None),
        response_json=(json.dumps(stash.get("response")) if has else None),
        agree_winner=agree_winner, user_grade=grade, note=note,
        context_available=has, created_at=_parse_created_at(stash), feedback_at=now,
    )
    db.session.merge(row)  # idempotent on re-submit for same analysis_id
    db.session.commit()
    try:
        from services.trade_analyzer.rag.ingest import ingest_feedback_row
        ingest_feedback_row(row)
    except Exception:
        pass
    return row
