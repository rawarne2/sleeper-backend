"""LLM provider interface and exception types."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar


class ProviderError(Exception):
    """Base for provider failures."""


class ProviderUnavailable(ProviderError):
    """Provider not configured / unreachable. Maps to 503."""


class ProviderTimeout(ProviderError):
    """Provider call exceeded timeout. Maps to 504."""


class LLMProvider(ABC):
    name: ClassVar[str]
    default_model: ClassVar[str]

    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str,
        timeout_s: int,
        **opts,
    ) -> str:
        """Return the raw text response from the LLM."""

    @abstractmethod
    def health_check(self) -> tuple[bool, str]:
        """Return (available, human-readable detail)."""
