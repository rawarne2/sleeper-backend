"""Ingest strategy KB and feedback rows into pgvector."""
from __future__ import annotations

import logging
from typing import Any

from models.entities import TradeFeedback
from services.trade_analyzer.prompt import SYSTEM_PROMPT
from services.trade_analyzer.rag.chunking import chunk_system_prompt
from services.trade_analyzer.rag.embeddings.registry import get_embedding_provider
from services.trade_analyzer.rag.feedback_doc import feedback_row_to_document
from services.trade_analyzer.rag import store

logger = logging.getLogger(__name__)


def _embed_texts(texts: list[str]) -> list[list[float]]:
    provider = get_embedding_provider()
    return provider.embed_documents(texts)


def ingest_strategy_kb(*, system_prompt: str | None = None) -> int:
    prompt = system_prompt if system_prompt is not None else SYSTEM_PROMPT
    docs = chunk_system_prompt(prompt)
    if not docs:
        return 0
    embeddings = _embed_texts([d["content"] for d in docs])
    store.delete_corpus("strategy_kb")
    return store.upsert_documents(docs, embeddings)


def ingest_feedback_row(row: TradeFeedback | dict[str, Any]) -> None:
    """Best-effort single-row ingest; never raises."""
    try:
        if isinstance(row, TradeFeedback):
            payload = {
                "id": row.id,
                "request_json": row.request_json,
                "context_json": row.context_json,
                "response_json": row.response_json,
                "agree_winner": row.agree_winner,
                "user_grade": row.user_grade,
                "note": row.note,
                "league_id": row.league_id,
                "provider": row.provider,
            }
        else:
            payload = row
        if payload.get("agree_winner") == "skipped":
            return
        doc = feedback_row_to_document(payload)
        if not doc["source_id"]:
            return
        embeddings = _embed_texts([doc["content"]])
        store.upsert_documents([doc], embeddings)
    except Exception:
        logger.warning("rag feedback ingest failed for %s", getattr(row, "id", row), exc_info=True)


def backfill_feedback() -> int:
    rows = (
        TradeFeedback.query
        .filter(TradeFeedback.context_available.is_(True))
        .filter(TradeFeedback.agree_winner != "skipped")
        .all()
    )
    count = 0
    for row in rows:
        ingest_feedback_row(row)
        count += 1
    return count
