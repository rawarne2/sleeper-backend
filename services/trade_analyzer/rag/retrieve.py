"""Retrieve relevant RAG chunks for an analyze call."""
from __future__ import annotations

from dataclasses import dataclass

from services.trade_analyzer.rag.config import rag_min_score, rag_top_k
from services.trade_analyzer.rag.embeddings.registry import get_embedding_provider
from services.trade_analyzer.rag import store


@dataclass(frozen=True)
class RetrievedChunk:
    corpus: str
    source_id: str
    content: str
    score: float


def retrieve_context(query: str) -> list[RetrievedChunk]:
    provider = get_embedding_provider()
    embedding = provider.embed_query(query)
    floor = rag_min_score()
    rows = store.search_similar(
        embedding,
        top_k=rag_top_k(),
        min_score=floor,
    )
    chunks: list[RetrievedChunk] = []
    for row in rows:
        score = float(row["score"])
        if score < floor:
            continue
        chunks.append(RetrievedChunk(
            corpus=row["corpus"],
            source_id=row["source_id"],
            content=row["content"],
            score=score,
        ))
    return chunks
