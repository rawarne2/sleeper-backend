"""Trade Analyzer route package."""
from fastapi import APIRouter

router = APIRouter(prefix="/api/trade-analyzer", tags=["Trade Analyzer"])

from . import providers as _providers  # noqa: F401,E402
from . import preview as _preview  # noqa: F401,E402
from . import analyze as _analyze  # noqa: F401,E402
from . import feedback as _feedback  # noqa: F401,E402
