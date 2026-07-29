"""Request-scoped context shared by the ASGI middleware and the logging filter."""
from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
