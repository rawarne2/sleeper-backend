"""Trade Analyzer route package."""
from flask import Blueprint

trade_analyzer_bp = Blueprint(
    "trade_analyzer", __name__, url_prefix="/api/trade-analyzer"
)

try:  # noqa: SIM105 — modules wired in later tasks
    from . import providers as _providers  # noqa: E402,F401
except ImportError:
    pass
try:
    from . import preview as _preview  # noqa: E402,F401
except ImportError:
    pass
try:
    from . import analyze as _analyze  # noqa: E402,F401
except ImportError:
    pass
