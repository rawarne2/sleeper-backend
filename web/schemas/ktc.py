"""Response schemas for the async KTC refresh endpoints.

Mirrors the 202 body built in ``routes/ktc/rankings.py::refresh_rankings`` and the
status projection in ``refresh_status`` (job record shape from
``services/ktc_refresh_async.py``). Enforced by ``tests/api/test_response_contracts.py``.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class KtcRefreshAccepted(BaseModel):
    """202 body of POST/PUT /api/ktc/refresh (async mode)."""
    model_config = ConfigDict(extra="forbid")
    accepted: bool
    status: Literal["queued"]
    job_id: str
    already_running: bool
    message: str
    poll_url: str
    is_redraft: bool
    league_format: Literal["1qb", "superflex"]
    tep_level: str
    hint: str


class KtcRefreshJobSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    players_count: Optional[int] = None
    database_saved_count: Optional[int] = None
    file_saved: Optional[bool] = None
    s3_uploaded: Optional[bool] = None


class KtcRefreshJobStatus(BaseModel):
    """GET /api/ktc/refresh/status/{job_id} — validated at runtime (route returns a dict)."""
    model_config = ConfigDict(extra="forbid")
    job_id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    created_at: str
    finished_at: Optional[str] = None
    league_format: str
    is_redraft: bool
    tep_level: str
    error: Optional[str] = None
    summary: Optional[KtcRefreshJobSummary] = None
