from services.trade_analyzer.rag.config import (
    rag_min_score,
    rag_top_k,
    trade_analyzer_rag_enabled,
)


def test_rag_disabled_by_default(monkeypatch):
    monkeypatch.delenv("TRADE_ANALYZER_RAG", raising=False)
    assert trade_analyzer_rag_enabled() is False


def test_rag_enabled_when_set(monkeypatch):
    monkeypatch.setenv("TRADE_ANALYZER_RAG", "1")
    assert trade_analyzer_rag_enabled() is True


def test_rag_top_k_default(monkeypatch):
    monkeypatch.delenv("TRADE_ANALYZER_RAG_TOP_K", raising=False)
    assert rag_top_k() == 5


def test_rag_min_score_default(monkeypatch):
    monkeypatch.delenv("TRADE_ANALYZER_RAG_MIN_SCORE", raising=False)
    assert rag_min_score() == 0.55
