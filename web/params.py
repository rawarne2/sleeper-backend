"""Shared query-param validation for routes (replaces utils.helpers.validate_parameters).

Kept as plain string params + manual checks (not Pydantic enums) so the exact 400
messages and lenient case-normalization of the current API are preserved. Routes
declare their own per-endpoint defaults via fastapi.Query and call validate_ktc_params.
"""
from __future__ import annotations

from dataclasses import dataclass

from web.errors import ApiError
from utils.helpers import normalize_tep_level


@dataclass(frozen=True)
class KtcParams:
    is_redraft: bool
    league_format: str
    tep_level: str | None


def validate_ktc_params(is_redraft: str, league_format: str, tep_level: str) -> KtcParams:
    if is_redraft.lower() not in ("true", "false"):
        raise ApiError('Invalid is_redraft parameter - must be "true" or "false"', 400)
    lf = league_format.lower()
    if lf not in ("1qb", "superflex"):
        raise ApiError("Invalid league_format parameter", 400)
    tep = normalize_tep_level(tep_level)
    if tep_level and tep is None:
        raise ApiError("Invalid tep_level parameter", 400)
    return KtcParams(is_redraft.lower() == "true", lf, tep)
