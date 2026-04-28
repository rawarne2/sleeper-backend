"""Redis cache defaults and env-backed settings."""
import os

DEFAULT_KTC_RANKINGS_REDIS_TTL_SECONDS = 86400
# Bundle is invalidated explicitly on KTC refresh and league sync, so a long
# TTL is safe and keeps the prewarm cron's effort durable between runs.
DEFAULT_DASHBOARD_LEAGUE_REDIS_TTL_SECONDS = 86400


def ktc_rankings_redis_ttl_seconds() -> int:
    return int(
        os.getenv(
            "KTC_RANKINGS_REDIS_TTL_SECONDS",
            str(DEFAULT_KTC_RANKINGS_REDIS_TTL_SECONDS),
        )
    )


def dashboard_league_redis_ttl_seconds() -> int:
    return int(
        os.getenv(
            "DASHBOARD_LEAGUE_REDIS_TTL_SECONDS",
            str(DEFAULT_DASHBOARD_LEAGUE_REDIS_TTL_SECONDS),
        )
    )
