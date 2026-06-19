# routes/valuations.py
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from scrapers.pipelines import ingest_valuations
from services.valuations import registry

router = APIRouter(prefix="/api/valuations", tags=["Maintenance"])


class ValuationsRefreshBody(BaseModel):
    league_format: str = "superflex"
    sources: Optional[list[str]] = None
    league_settings: dict[str, Any] = {}
    season: str = "2026"


@router.post("/refresh")
def refresh_valuations(body: ValuationsRefreshBody | None = None):
    payload = body or ValuationsRefreshBody()
    sources = payload.sources or registry.known_sources()
    results = ingest_valuations(
        sources,
        season=str(payload.season),
        league_format=payload.league_format,
        league_settings=payload.league_settings,
    )
    return {"results": results}
