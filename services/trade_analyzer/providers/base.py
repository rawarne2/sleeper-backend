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


class ProviderRateLimited(ProviderError):
    """Upstream LLM quota / rate limit (HTTP 429). Maps to 429."""

    def __init__(self, message: str, *, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


def _exc_status_code(exc: Exception) -> int | None:
    for attr in ("code", "status_code", "status"):
        val = getattr(exc, attr, None)
        if isinstance(val, int):
            return val
    return None


def is_provider_rate_limited(exc: Exception) -> bool:
    """True when an SDK/HTTP error indicates upstream quota or rate limiting."""
    status = _exc_status_code(exc)
    if status == 429:
        return True
    name = type(exc).__name__
    if name in ("ResourceExhausted", "TooManyRequests", "RateLimitError"):
        return True
    msg = str(exc).lower()
    return any(
        token in msg
        for token in (
            "429",
            "too many requests",
            "rate limit",
            "rate_limit",
            "quota exceeded",
            "resource exhausted",
        )
    )


def is_provider_timeout(exc: Exception) -> bool:
    name = type(exc).__name__
    msg = str(exc).lower()
    return (
        "Timeout" in name
        or "DeadlineExceeded" in name
        or "deadline exceeded" in msg
    )


def map_provider_call_error(
    exc: Exception,
    *,
    provider: str,
    timeout_s: int,
) -> None:
    """Re-raise *exc* as the appropriate Provider* subclass."""
    if is_provider_timeout(exc):
        raise ProviderTimeout(
            f"{provider} timeout after {timeout_s}s: {exc}"
        ) from exc
    if is_provider_rate_limited(exc):
        raise ProviderRateLimited(
            f"{provider} rate limit reached (HTTP 429). "
            "Wait a minute and try again, or choose another provider/model.",
            retry_after_seconds=60,
        ) from exc
    raise ProviderError(f"{provider} call failed: {exc}") from exc


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
