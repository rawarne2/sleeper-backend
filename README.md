# Sleeper Backend API

A Flask API for fantasy football data across KeepTradeCut (KTC) and Sleeper, including rankings, league data, research, dashboard payloads, and maintenance pipelines.

## Documentation

- **Production**: <https://sleeper-backend.vercel.app/docs>
- **Local**: <http://localhost:5001/docs>

### Additional Docs

- **[API_DOCUMENTATION.md](API_DOCUMENTATION.md)** -- Full API reference with endpoint details, parameters, request/response schemas, and usage examples for every KTC and Sleeper endpoint.
- **[OPENAPI_README.md](OPENAPI_README.md)** -- How the interactive Swagger UI and OpenAPI spec are set up, plus instructions for accessing `/docs` and `/openapi.json`.
- **[tests/README.md](tests/README.md)** -- Test directory layout and instructions for running tests locally and in Docker.

## 🚀 Features

- **KTC Integration**: Player rankings and trade values from KeepTradeCut
- **Sleeper Integration**: Player profiles and league management from Sleeper API
- **TEP Support**: Tight End Premium scoring (tep, tepp, teppp)
- **Multiple Formats**: 1QB and Superflex league support
- **Dynasty & Redraft**: Both ranking types supported
- **Weekly Stats**: Fantasy points and roster data from Sleeper matchups
- **Season Averages**: Calculate player averages (weeks 1–17; week 18 excluded)
- **Database Caching**: Fast response times with persistent storage

## Weekly stats

Sleeper matchup data per week; season averages and dashboard per-player `stats` use weeks 1–17 (week 18 excluded). Flow: seed `/api/sleeper/league/{id}/stats/seed`, then `GET` / `POST` / `PUT` on `/api/sleeper/league/{id}/stats/week/{week}`. Examples: [API_DOCUMENTATION.md](API_DOCUMENTATION.md).

## Quick Start

### Option 1: Docker (Production-Ready)

Use the provided `docker-compose.sh` script to run everything in containers with PostgreSQL:

```bash
# Start the application (PostgreSQL + Flask)
./docker-compose.sh up

# Check application status
./docker-compose.sh status

# View logs
./docker-compose.sh logs

# Stop the application
./docker-compose.sh down

# Clean up containers
./docker-compose.sh clean
```

The application will be available at `http://localhost:5001`.

**📖 Interactive API Documentation**: `http://localhost:5001/docs/`
**📄 OpenAPI Specification**: `http://localhost:5001/openapi.json`

**Testing from mobile (same network):** Run the backend in Docker as above, then open your Vite app on your phone using your computer’s IP (e.g. `http://192.168.1.5:5173`). Point the frontend’s API base URL at that same IP and port 5001 (e.g. `http://192.168.1.5:5001`). CORS allows local network origins (192.168.x.x, 10.x.x.x, 172.16–31.x.x).

### Option 2: Local Development (Simple)

For local development with SQLite (no database server needed):

```bash
# Install dependencies
pip install -r requirements.txt

# Start the application (uses SQLite by default)
./startup.sh
```

The application will be available at `http://localhost:5001`.

**What happens:**

- ✅ Creates a local `sleeper_local.db` SQLite file
- ✅ No database installation required
- ✅ Perfect for development and testing
- ✅ Uses Gunicorn for production-ready performance

### Option 3: Local Development with Supabase (No Local DB)

To develop locally while connecting to the production Vercel/Supabase database (no Docker or local Postgres required):

1. Copy `.env.example` to `.env` and set `DATABASE_URL` to your Supabase connection string:

2. Start the application:

   ```bash
   ./startup.sh
   ```

The app reads `DATABASE_URL` from the environment and connects directly to Supabase -- no Docker or local Postgres needed.

## Database

SQLAlchemy supports **SQLite** (default local/tests) and **PostgreSQL** (Docker/Vercel). Set `DATABASE_URL` in `.env` for remote Postgres; see `.env.example`.

## Database migrations

Schema changes use Flask-Migrate (Alembic).

**After changing a model, generate a migration:**
```bash
flask --app app db migrate -m "describe the change"
# Review migrations/versions/<hash>_describe_the_change.py
flask --app app db upgrade
```

**Apply in production before deploying code that requires the schema change:**
```bash
POSTGRES_URL=<prod_url> flask --app vercel_app db upgrade
```

Raw SQL files in `sql/migrations/` remain for reference; use `flask db migrate` going forward.

## API quick try

- **Docs:** `http://localhost:5001/docs/` (root redirects); **OpenAPI:** `/openapi.json`.
- **KTC refresh:** `POST`/`PUT /api/ktc/refresh` usually returns **202** (background job); add `sync=1` to block, or poll `GET /api/ktc/refresh/status/{job_id}`.

```bash
curl http://localhost:5001/api/ktc/health
curl -X POST "http://localhost:5001/api/ktc/refresh?league_format=superflex&is_redraft=false&tep_level=tep"
curl "http://localhost:5001/api/ktc/rankings?league_format=superflex&is_redraft=false&tep_level=tep"
```

### Trade Analyzer

Three endpoints under `/api/trade-analyzer`:

- `GET /providers` — list configured LLM providers, models, rate limits, and `enabled`.
- `POST /preview` — build slim LLM `context` + prompts (no model call).
- `POST /analyze` — run the trade through the provider; returns winner, grades, and per-side breakdown.

Request body: `league_id`, `season`, `side_a` / `side_b` (`roster_id`, `player_ids`, `pick_ids`); optional `ktc` (`league_format`, `tep_level`, `is_redraft`), `additional_context`, `provider`, `model`. League must be in the DB (`POST /api/sleeper/league/{id}`) with KTC merge for the requested format.

The **user prompt** is compact JSON: single KTC variant (no `tep`/`tepp`/`teppp` nests), `league.research_week` + `market_*` on trade and roster players, slim roster rows (`name` only for trade players; no position/positional_tier), picks as `label` + `ktc_value`, `trade.side_*_outgoing` only (incoming = other side's outgoing), no `trade_summary`, full bench depth for player trades. See [docs/trade-analyzer-payload.md](docs/trade-analyzer-payload.md).

Sample **analyze** shape without an API key: `provider: "echo"` (fixture in `tests/fixtures/data/trade_analyzer_echo.json`). There is no GET sample endpoint.

```bash
# Input context only (no LLM)
curl -sS -X POST http://localhost:5001/api/trade-analyzer/preview \
  -H "Content-Type: application/json" \
  -d '{"league_id":"1210364682523656192","season":"2026","ktc":{"league_format":"superflex","is_redraft":false,"tep_level":"tep"},"side_a":{"roster_id":3,"player_ids":["4881"],"pick_ids":[]},"side_b":{"roster_id":7,"player_ids":["4034"],"pick_ids":[]},"provider":"echo"}'

# Example analyze response (echo provider)
curl -sS -X POST http://localhost:5001/api/trade-analyzer/analyze \
  -H "Content-Type: application/json" \
  -d '{"league_id":"1210364682523656192","season":"2026","ktc":{"league_format":"superflex","is_redraft":false,"tep_level":"tep"},"side_a":{"roster_id":3,"player_ids":["4881"],"pick_ids":[]},"side_b":{"roster_id":7,"player_ids":["4034"],"pick_ids":[]},"provider":"echo","model":"echo"}'
```

`TRADE_ANALYZER_DEBUG_LOG=1` logs full system/user prompts on analyze.

## Available scripts

| Path | Purpose |
|------|---------|
| `docker-compose.sh` | PostgreSQL + app containers (up, down, logs, status, clean) |
| `startup.sh` | Local Flask (SQLite by default) |
| `run_tests.sh` | Pytest via Docker (see [tests/README.md](tests/README.md)) |
| `scripts/` | DB setup/reset, `ktc-scrape.py`, `manual_player_merge.py`, `cleanup_invalid_players.py`, etc. (run from repo root with venv active) |
