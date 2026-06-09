"""Split strategy guidance into embeddable chunks."""
from __future__ import annotations

import re
from typing import Any

_H2_SPLIT = re.compile(r"(?=^## )", re.MULTILINE)


def _slug(header: str) -> str:
    text = header.removeprefix("## ").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return slug[:64] or "section"


def chunk_system_prompt(system_prompt: str) -> list[dict[str, Any]]:
    """Return strategy_kb documents from a ##-sectioned system prompt."""
    parts = _H2_SPLIT.split(system_prompt.strip())
    chunks: list[dict[str, Any]] = []
    for part in parts:
        part = part.strip()
        if not part.startswith("## "):
            continue
        first_line = part.split("\n", 1)[0]
        section = first_line.removeprefix("## ").strip()
        chunks.append({
            "corpus": "strategy_kb",
            "source_id": _slug(first_line),
            "content": part,
            "metadata": {"section": section},
        })
    return chunks
