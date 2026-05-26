"""Trade Analyzer route package."""
from flask import Blueprint

trade_analyzer_bp = Blueprint(
    "trade_analyzer", __name__, url_prefix="/api/trade-analyzer"
)

from . import providers as _providers  # noqa: F401
from . import preview as _preview  # noqa: F401
from . import analyze as _analyze  # noqa: F401
