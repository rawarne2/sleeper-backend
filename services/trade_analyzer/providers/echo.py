"""Test-only provider that returns a fixture JSON."""
from __future__ import annotations

import pathlib

from .base import LLMProvider

_FIXTURE = (
    pathlib.Path(__file__).resolve().parents[3]
    / "tests" / "fixtures" / "data" / "trade_analyzer_echo.json"
)


class EchoProvider(LLMProvider):
    name = "echo"
    default_model = "echo"

    def generate(self, system_prompt, user_prompt, *, model, timeout_s, **opts):
        with _FIXTURE.open(encoding="utf-8") as f:
            return f.read()

    def health_check(self):
        return True, "echo provider (test-only)"
