"""Redis cache defaults and env-backed settings."""
import os

DEFAULT_KTC_RANKINGS_REDIS_TTL_SECONDS = 86400
DEFAULT_DASHBOARD_LEAGUE_REDIS_TTL_SECONDS = 90


def ktc_rankings_redis_ttl_seconds() -> int:
    return int(
        os.getenv(
            "KTC_RANKINGS_REDIS_TTL_SECONDS",
            str(DEFAULT_KTC_RANKINGS_REDIS_TTL_SECONDS),
        )
    )


def dashboard_league_redis_ttl_seconds() -> int:
    """Short TTL: bundle mixes DB league snapshot + KTC + research; stale data is acceptable briefly."""
    return int(
        os.getenv(
            "DASHBOARD_LEAGUE_REDIS_TTL_SECONDS",
            str(DEFAULT_DASHBOARD_LEAGUE_REDIS_TTL_SECONDS),
        )
    )
