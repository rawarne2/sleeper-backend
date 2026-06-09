#!/usr/bin/env python3
"""Ingest strategy KB chunks from SYSTEM_PROMPT into pgvector."""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app import app
from services.trade_analyzer.rag.embeddings.registry import get_embedding_provider
from services.trade_analyzer.rag.ingest import ingest_strategy_kb


def main() -> int:
    with app.app_context():
        ok, detail = get_embedding_provider().health()
        if not ok:
            print(f"embedding provider unavailable: {detail}")
            return 1
        count = ingest_strategy_kb()
        print(f"ingested {count} strategy_kb chunks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
