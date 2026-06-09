from services.trade_analyzer.prompt import SYSTEM_PROMPT
from services.trade_analyzer.rag.chunking import chunk_system_prompt


def test_chunk_system_prompt_splits_on_h2_headers():
    chunks = chunk_system_prompt(SYSTEM_PROMPT)
    assert len(chunks) >= 8
    ids = {c["source_id"] for c in chunks}
    assert "grading" in ids
    assert all(c["corpus"] == "strategy_kb" for c in chunks)
    assert all("##" in c["content"] for c in chunks)


def test_chunk_source_ids_are_stable():
    a = chunk_system_prompt(SYSTEM_PROMPT)
    b = chunk_system_prompt(SYSTEM_PROMPT)
    assert [x["source_id"] for x in a] == [x["source_id"] for x in b]
