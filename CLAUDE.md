# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common commands

App entrypoints (port `5001` everywhere — port 5000 is intentionally avoided):
- `./startup.sh` — local Flask via Gunicorn; defaults `DATABASE_URL=sqlite:///sleeper_local.db` if unset. Set `REMOTE_DEBUG=1` to enable debugpy on port 5678.
- `./docker-compose.sh up` — Postgres + Redis + Flask in containers. Other subcommands: `down`, `logs`, `status`, `clean`, `redis-cli`, `redis-keys`, `warm-cache`. **Ask the user before running the app.**
- Vercel runs `vercel_app.py` (not `app.py`); `wsgi.py` is the Gunicorn target.

Tests (use `./run_tests.sh` as the canonical runner — it builds the Docker image and runs pytest with `TEST_DATABASE_URI=sqlite:///:memory:`):
- `./run_tests.sh` — all tests in Docker.
- `./run_tests.sh tests/unit/` / `tests/api/` / `tests/integration/` — by directory; or `-m unit|api|integration` by marker (markers auto-applied by `tests/conftest.py::pytest_collection_modifyitems` based on path).
- `./run_tests_local.sh [path or args]` — same, but uses the local venv.
- Single test: `./run_tests_local.sh tests/api/ktc/test_rankings.py::TestRankings::test_x` (or pass through Docker runner).
- After backend dependency updates, run `pip install -r requirements.txt` in the venv before tests.

Operational scripts (run from repo root with venv active):
- `scripts/cleanup_invalid_players.py` — dry run by default; `--execute` performs batched ORM deletes (cascades child KTC rows). Loads `.env` and unsets `TEST_DATABASE_URI` when `DATABASE_URL` is set so it targets the same DB as the app, not pytest SQLite.
- `scripts/seed_three_leagues.py`, `scripts/manual_player_merge.py`, `scripts/ktc-scrape.py`, `scripts/reset_db.py`, `scripts/setup_postgres.py`.

## Flask entrypoints

`app.py` (local) and `vercel_app.py` (serverless on Vercel) share blueprint registration, CORS, Compress, Swagger, and Flask-Migrate setup through `app_factory.py::create_app`. Each entrypoint is responsible only for its own DB URL resolution and `engine_options`:

- `app.py` reads `TEST_DATABASE_URI` then `DATABASE_URL` (via `utils/constants.DATABASE_URI`); pooled engine with `pool_pre_ping`, `pool_recycle=3600`, `pool_size=10`.
- `vercel_app.py` resolves the DB URL from the first set among `POSTGRES_URL`, `POSTGRES_PRISMA_URL`, `DATABASE_URL`, `POSTGRES_URL_NON_POOLING`; uses `NullPool` with `sslmode=require` and a 15s `statement_timeout`. It strips non-libpq query params from the URL and rewrites `postgres://` → `postgresql://`.
- Both engines pass `connect_args={"options": "-c timezone=UTC"}`. Postgres `timestamp without time zone` columns can read shifted by an hour if a session is not on UTC, so do not remove this.

## Architecture

Flask + SQLAlchemy with one ORM module. Entities live in `models/entities.py` (`Player`, plus Sleeper league/roster/user/research/weekly tables); `models.extensions` exposes the `db` instance. `import models.entities` is required from both entrypoints to register mappers before `db.create_all()`.

Blueprints are registered through `routes/registry.py` (`routes/__init__.py` is intentionally empty). Adding a new route surface means: create the module under `routes/...`, import its blueprint in `routes/registry.py`, and update `openapi.yaml` + `routes/swagger_config.py` examples + `README.md` so live prefixes match.

Layered structure:
- `routes/` — HTTP layer; uses `routes/helpers.py::json_api_error` (returns `{status, error, timestamp (RFC 3339), details?}`) and `with_error_handling` for unexpected → 500. Validation/client errors use this envelope; do not invent ad-hoc error shapes.
- `services/` — orchestration (e.g. async KTC refresh in `services/ktc_refresh_async.py`, `daily_refresh.py`).
- `managers/` — DB writers and merge logic (`database_manager.py`, `player_merger.py`, `file_manager.py`).
- `scrapers/` — external fetchers (`ktc_scraper.py`, `sleeper_scraper.py`) and `pipelines.py` glue (preloads eligible Sleeper rows from DB via `load_sleeper_players_for_merge_from_db` to avoid N+1).
- `cache/` — Redis: `redis_rankings.py` for `GET /api/ktc/rankings`, `redis_dashboard.py` for the dashboard bundle. TTLs in `cache/settings.py` (`KTC_RANKINGS_REDIS_TTL_SECONDS`, `DASHBOARD_LEAGUE_REDIS_TTL_SECONDS`; both default 86400). Both responses set `X-*-Cache: HIT|MISS` headers; dashboard adds `X-Dashboard-League-Payload-Bytes` and `ms_*` timing fields in logs.
- `utils/` — `constants.py` (env-derived config and league/week constants — week 18 excluded from season aggregates via `SLEEPER_STATS_AGGREGATE_WEEK_MIN/MAX`), `cors.py`, `datetime_serialization.py`, `player_eligibility.py`.
- `data_types/` — typed DTOs.
- `sql/` — DDL (`ddl_performance_indexes.sql`) and migrations under `sql/migrations/` (e.g. `20260426_drop_duplicate_player_fields.sql` drops legacy KTC `heightFeet`/`heightInches`/`birthday` in favor of Sleeper `height`/`birth_date` — `UndefinedColumn` errors in production usually mean migrations and deployed code are out of step).

## Domain conventions

- KTC rankings come in `oneQB`/`superflex` × `tep`/`tepp`/`teppp` variants; `routes/helpers.py::filter_players_by_format` mutates shallow copies of the values blocks rather than deep-copying. Do not refactor it to mutate the underlying ORM dicts.
- Sleeper `position == "RDP"` rows (rookie/draft picks; `SLEEPER_POSITION_RDP`) are valid and should be persisted; `search_rank == 9_999_999` (`SLEEPER_SEARCH_RANK_EXCLUDE`) is a sentinel and should be excluded.
- Weekly stats (`SleeperWeeklyData`) are keyed by `(season, week, league_type, player_id)` — **not** `league_id` — so once one league is refreshed for a season/league_type, every league reads the same per-player stats. The dashboard never scrapes weekly stats inline; the nightly cron or `scripts/seed_three_leagues.py` populates them.
- After Sleeper saves, `Player` rows not in the export are pruned via ORM cascade. Persisted players need a `match_key`.
- API instants are serialized as RFC 3339 with explicit `Z`/numeric offset (use `utils.datetime_serialization`).
- `POST`/`PUT /api/sleeper/league/{id}` returns **404** on Sleeper scrape failure and **500** on persistence failure — not 200 with an error in the body. League refresh path is `POST /api/sleeper/league/{id}` (not `.../refresh`).
- `POST /api/ktc/refresh` returns **202** with `job_id`/`poll_url` for async work; clients can pass `sync=1` to block. The `sleeper-dashboard` frontend polls `GET /api/ktc/refresh/status/<job_id>` until a terminal state before reloading the bundle.
- Trade analyzer slim LLM context and curl examples: `docs/trade-analyzer-payload.md`. Sample analyze: `provider: echo` or `tests/fixtures/data/trade_analyzer_echo.json` (no GET sample route).
- **Trade analyzer perf:** Gemini uses the `google-genai` SDK with `thinking_budget=0` by default (raise via `TRADE_ANALYZER_GEMINI_THINKING_BUDGET` for deeper reasoning at +10–30s latency). All providers use the canonical `TRADE_ANALYZER_JSON_SCHEMA` for structured output. Provider health checks are cached in-process only (`services/trade_analyzer/health_cache.py`, 60s success / 5s failure) — there is intentionally no Redis or IndexedDB cache for analysis results so injuries/news flow through immediately. Ownership + `research_meta` are loaded once in `_load_league.py` and threaded through `build_context` and `load_stats_with_trajectory`'s `max_week` arg; do not requery `SleeperWeeklyData` from those callers.

## Maintenance / cron

`/api/maintenance/nightly-sync` (and `/prewarm`, same prewarm step) require `Authorization: Bearer <CRON_SECRET>` when `VERCEL_ENV=production` (header-only auth disabled in prod). Pipeline order: KTC formats → leagues → research; research seasons come from each league's API `season`. `_prewarm_dashboard_caches` runs after the pipeline unless `skip_prewarm`. `POST /api/sleeper/refresh` (60s+ Sleeper NFL ingest) is operator-only and **not** part of any scheduled run. `vercel.json` defines one daily cron at `30 15 * * *` UTC (Vercel Hobby allows ≤1 run/day per job). When calling maintenance in prod, target the deployed backend origin, not the Supabase REST host.

## Conventions to follow

- Keep code comments minimal; do not narrate what code already states. When simplifying, remove unused imports.
- Keep `requirements.txt` to dependency pins (no commentary blocks). Keep `.env.example` concise: short section headers, one-line hints.
- Commit messages: short, sentence-style, with commas separating the main changes (no long paragraph or bullet list in the subject).
- Don't add OpenAPI/Swagger `license` metadata unless a matching root `LICENSE` file exists.
- Don't suggest `sh -n` as a workflow — it only parses syntax.
- Run scripts individually (e.g. `./docker-compose.sh up`, then `./startup.sh`); avoid chaining multiple scripts on one line unless asked.
