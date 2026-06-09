"""pgvector persistence for RAG documents."""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from models.extensions import db

_EMBEDDING_DIM = 768


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.8f}" for v in values) + "]"


def delete_corpus(corpus: str) -> None:
    db.session.execute(
        text("DELETE FROM rag_documents WHERE corpus = :corpus"),
        {"corpus": corpus},
    )
    db.session.commit()


def upsert_documents(docs: list[dict[str, Any]], embeddings: list[list[float]]) -> int:
    if len(docs) != len(embeddings):
        raise ValueError("docs and embeddings length mismatch")
    if not docs:
        return 0

    now = datetime.now(UTC)
    for doc, embedding in zip(docs, embeddings):
        if len(embedding) != _EMBEDDING_DIM:
            raise ValueError(f"expected {_EMBEDDING_DIM}-dim embedding, got {len(embedding)}")
        db.session.execute(
            text(
                """
                INSERT INTO rag_documents (id, corpus, source_id, content, metadata, embedding, created_at)
                VALUES (:id, :corpus, :source_id, :content, CAST(:metadata AS jsonb), CAST(:embedding AS vector), :created_at)
                ON CONFLICT (corpus, source_id) DO UPDATE SET
                  content = EXCLUDED.content,
                  metadata = EXCLUDED.metadata,
                  embedding = EXCLUDED.embedding,
                  created_at = EXCLUDED.created_at
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "corpus": doc["corpus"],
                "source_id": doc["source_id"],
                "content": doc["content"],
                "metadata": json.dumps(doc.get("metadata") or {}),
                "embedding": _vector_literal(embedding),
                "created_at": now,
            },
        )
    db.session.commit()
    return len(docs)


def search_similar(
    query_embedding: list[float],
    *,
    top_k: int,
    min_score: float,
) -> list[dict[str, Any]]:
    if len(query_embedding) != _EMBEDDING_DIM:
        raise ValueError(f"expected {_EMBEDDING_DIM}-dim query embedding")

    try:
        rows = db.session.execute(
            text(
                """
                SELECT corpus, source_id, content, metadata,
                       1 - (embedding <=> CAST(:embedding AS vector)) AS score
                FROM rag_documents
                ORDER BY embedding <=> CAST(:embedding AS vector)
                LIMIT :top_k
                """
            ),
            {
                "embedding": _vector_literal(query_embedding),
                "top_k": top_k,
            },
        ).mappings().all()
    except ProgrammingError:
        db.session.rollback()
        return []

    hits: list[dict[str, Any]] = []
    for row in rows:
        score = float(row["score"] or 0.0)
        if score < min_score:
            continue
        hits.append({
            "corpus": row["corpus"],
            "source_id": row["source_id"],
            "content": row["content"],
            "metadata": row["metadata"] or {},
            "score": score,
        })
    return hits
