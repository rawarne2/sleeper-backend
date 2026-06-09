from services.trade_analyzer.rag.retrieve import RetrievedChunk, retrieve_context


def test_retrieve_filters_by_min_score(monkeypatch):
    monkeypatch.setattr(
        "services.trade_analyzer.rag.retrieve.get_embedding_provider",
        lambda: type("P", (), {"embed_query": lambda self, q: [0.0] * 768})(),
    )
    monkeypatch.setattr(
        "services.trade_analyzer.rag.retrieve.store.search_similar",
        lambda *a, **k: [
            {"corpus": "strategy_kb", "source_id": "a", "content": "hi", "score": 0.7},
            {"corpus": "feedback", "source_id": "b", "content": "lo", "score": 0.3},
        ],
    )
    chunks = retrieve_context("test query")
    assert len(chunks) == 1
    assert chunks[0].source_id == "a"
    assert isinstance(chunks[0], RetrievedChunk)
