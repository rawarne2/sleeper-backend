"""Cron/Bearer auth helper for maintenance endpoints (ports _cron_authorized)."""
import os

from starlette.requests import Request
from utils.helpers import setup_logging

logger = setup_logging(__name__)

CRON_AUTH_HINT = (
    "Set CRON_SECRET in the server environment and send "
    "Authorization: Bearer <CRON_SECRET>"
)


def cron_authorized(request: Request) -> bool:
    """
    Authorize a request from Vercel Cron.

    Vercel Cron sends ``Authorization: Bearer <CRON_SECRET>`` and ``x-vercel-cron: 1``.
    Production (``VERCEL_ENV=production``) requires ``CRON_SECRET`` to be set; the
    header alone is not sufficient (headers are spoofable).

    Non-production: if ``CRON_SECRET`` is unset, allow requests that include
    ``x-vercel-cron`` for local/preview testing only.
    """
    secret = (os.getenv("CRON_SECRET") or "").strip()
    vercel_env = (os.getenv("VERCEL_ENV") or "").strip().lower()
    auth = (request.headers.get("Authorization") or "").strip()
    is_vercel_cron = bool(request.headers.get("x-vercel-cron"))

    if vercel_env == "production" and not secret:
        logger.warning(
            "cron auth failed: CRON_SECRET is required when VERCEL_ENV=production"
        )
        return False

    if secret:
        if len(auth) >= 7 and auth[:7].lower() == "bearer ":
            if auth[7:].strip() == secret:
                return True
        logger.warning(
            "cron auth failed: bearer token missing or mismatch (vercel_cron=%s, has_auth=%s)",
            is_vercel_cron,
            bool(auth),
        )
        return False

    if is_vercel_cron:
        logger.warning(
            "cron auth: CRON_SECRET unset; allowing because x-vercel-cron header is present"
        )
        return True

    logger.warning(
        "cron auth failed: CRON_SECRET unset and request lacks x-vercel-cron header"
    )
    return False
