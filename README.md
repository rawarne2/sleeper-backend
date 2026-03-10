# Sleeper Backend API

A Flask-based API for scraping and serving fantasy football player rankings from KeepTradeCut (KTC).

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
- **Season Averages**: Calculate player averages (weeks 1-16)
- **Database Caching**: Fast response times with persistent storage

## 📊 Weekly Stats

The project now includes weekly fantasy football stats functionality that fetches data from Sleeper league matchups. This allows you to:

- **Track weekly performance**: Get fantasy points for all players each week
- **Calculate season averages**: Compute player averages across weeks 1-16 (regular season)
- **Monitor roster changes**: Track which players started vs. sat each week
- **Historical analysis**: Store and query data across multiple seasons

### Weekly Stats Endpoints

```bash
# Seed league information (run once per league)
POST /api/sleeper/league/{league_id}/stats/seed

# Refresh weekly stats for a specific week
POST /api/sleeper/league/{league_id}/stats/week/{week}

# Get weekly stats for a specific week
GET /api/sleeper/league/{league_id}/stats/week/{week}

# Get season averages (weeks 1-16 only)
GET /api/sleeper/league/{league_id}/stats/week/{week}?average=true
```

### Example Usage

```bash
# 1. First, seed Sleeper player data (foundation - takes 30-60 seconds)
curl -X POST "http://localhost:5001/api/sleeper/refresh"

# 2. Then, merge KTC rankings into existing Sleeper players (fast - takes 5-10 seconds)
curl -X POST "http://localhost:5001/api/ktc/refresh/all"

# 3. Seed your league (replace with your league ID, league name, and season)
curl -X POST "http://localhost:5001/api/sleeper/league/1050831680350568448/stats/seed" \
  -H "Content-Type: application/json" \
  -d '{"league_name": "My League", "season": "2024", "league_type": "dynasty"}'

# 4. Refresh week 1 stats
curl -X POST "http://localhost:5001/api/sleeper/league/1050831680350568448/stats/week/1?season=2024&league_type=dynasty"

# 5. Get week 1 stats
curl "http://localhost:5001/api/sleeper/league/1050831680350568448/stats/week/1?season=2024&league_type=dynasty"

# 6. Get season averages
curl "http://localhost:5001/api/sleeper/league/1050831680350568448/stats/week/1?season=2024&league_type=dynasty&average=true"
```

### Data Structure

Weekly stats include:

- **Player ID**: Sleeper player identifier
- **Fantasy Points**: Decimal points scored (e.g., 26.08)
- **Roster ID**: Which team the player belongs to
- **Starter Status**: Whether the player was in the starting lineup
- **Week & Season**: Temporal context for the data

### Notes

- **Weeks 1-16**: Only regular season weeks are used for average calculations
- **Data Persistence**: All stats are stored in the database for fast retrieval
- **League Setup**: Run the seed endpoint once per league before fetching stats
- **Cron Jobs**: Future implementation will include automated weekly updates

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

## Database Strategy

This application uses a **dual-database approach** for optimal development and deployment:

| Database | Used For | Benefits |
|----------|----------|----------|
| **SQLite** | • Local development<br>• Unit tests<br>• CI/CD testing | • Zero setup required<br>• Fast test execution<br>• File-based (easy backup/sharing) |
| **PostgreSQL** | • Production (Vercel)<br>• Docker containers<br>• Team development | • Better concurrency<br>• Production scalability<br>• Advanced features for future AI |

**Key Points:**

- Code is **database-agnostic** using SQLAlchemy ORM
- Tests automatically use SQLite in-memory for speed
- Production deployments (Vercel) require PostgreSQL
- Local development can use SQLite, local PostgreSQL, or connect directly to the Vercel/Supabase database by setting `DATABASE_URL` in `.env` (see `.env.example`)

## Interactive API Documentation

The application now includes **built-in interactive API documentation** powered by Swagger/OpenAPI:

- **📖 Interactive Documentation**: Visit `http://localhost:5001/docs/` to explore and test all API endpoints directly in your browser
- **🏠 Auto-redirect**: The root URL `http://localhost:5001/` automatically redirects to the documentation
- **📄 OpenAPI Spec**: Machine-readable specification available at `http://localhost:5001/openapi.json`

**Benefits of Interactive Documentation:**

- ✅ Test all endpoints directly from the web interface
- ✅ View detailed request/response schemas
- ✅ No need to remember curl syntax
- ✅ Real-time API validation and examples

## Using the API

You can use the API in two ways:

### Option 1: Interactive Documentation (Recommended)

Visit `http://localhost:5001/docs/` in your browser to test endpoints interactively.

### Option 2: Command Line (Advanced Users)

#### 1. Check Health

```bash
curl http://localhost:5001/api/ktc/health
```

#### 2. Load Rankings Data

```bash
# Superflex redraft rankings
curl -X PUT "http://localhost:5001/api/ktc/refresh?league_format=superflex&is_redraft=true&tep_level=tep"

curl -X POST "http://localhost:5001/api/ktc/refresh?league_format=superflex&is_redraft=true&tep_level=tep"

# 1QB dynasty rankings
curl -X PUT "http://localhost:5001/api/ktc/refresh?league_format=1qb&is_redraft=false&tep_level=tep"

curl -X POST "http://localhost:5001/api/ktc/refresh?league_format=1qb&is_redraft=false&tep_level=tep"
```

#### 3. Get Rankings

```bash
# Get the rankings you just loaded (same for both PUT and POST)
curl "http://localhost:5001/api/ktc/rankings?league_format=superflex&is_redraft=true&tep_level=tep"
```

## Available Scripts

| Script | Purpose |
|--------|---------|
| `docker-compose.sh` | Manage Docker containers with PostgreSQL (up, down, logs, status, clean) |
| `startup.sh` | Start Flask application locally with SQLite |
| `run_tests.sh`
