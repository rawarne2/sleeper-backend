"""Prompt token estimation for trade-analyzer logging and API metadata."""
from __future__ import annotations

from typing import Dict


def estimate_prompt_tokens(system_prompt: str, user_prompt: str) -> Dict[str, int]:
    """Rough token count (~4 chars/token) for system + user prompts."""
    system_chars = len(system_prompt or "")
    user_chars = len(user_prompt or "")
    total_chars = system_chars + user_chars
    estimated = max(1, total_chars // 4)
    return {
        "prompt_tokens_estimated": estimated,
        "system_chars": system_chars,
        "user_chars": user_chars,
    }
