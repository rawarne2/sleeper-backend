# Sleeper Backend API

A Flask-based API for scraping and serving fantasy football player rankings from KeepTradeCut (KTC).

## Documentation

- **Production** `https://sleeper-backend.vercel.app/docs`
- **Local**`http://localhost:5000/docs`

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
POST /api/sleeper/league/{league_id}/stats/week/{week}/refresh

# Get weekly stats for a specific week
GET /api/sleeper/league/{league_id}/stats/week/{week}

# Get season averages (weeks 1-16 only)
GET /api/sleeper/league/{league_id}/stats/week/{week}?average=true
```

### Example Usage

```bash
# 1. First, seed Sleeper player data (foundation - takes 30-60 seconds)
curl -X POST "http://localhost:5000/api/sleeper/refresh"

# 2. Then, merge KTC rankings into existing Sleeper players (fast - takes 5-10 seconds)
curl -X POST "http://localhost:5000/api/ktc/refresh/all"

# 3. Seed your league (replace with your league ID, league name, and season)
curl -X POST "http://localhost:5000/api/sleeper/league/1050831680350568448/stats/seed" \
  -H "Content-Type: application/json" \
  -d '{"league_name": "My League", "season": "2024", "league_type": "dynasty"}'

# 4. Refresh week 1 stats
curl -X POST "http://localhost:5000/api/sleeper/league/1050831680350568448/stats/week/1/refresh?season=2024&league_type=dynasty"

# 5. Get week 1 stats
curl "http://localhost:5000/api/sleeper/league/1050831680350568448/stats/week/1?season=2024&league_type=dynasty"

# 6. Get season averages
curl "http://localhost:5000/api/sleeper/league/1050831680350568448/stats/week/1?season=2024&league_type=dynasty&average=true"
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

The application will be available at `http://localhost:5000`

**📖 Interactive API Documentation**: `http://localhost:5000/docs/`
**📄 OpenAPI Specification**: `http://localhost:5000/openapi.json`

### Option 2: Local Development (Simple)

For local development with SQLite (no database server needed):

```bash
# Install dependencies
pip install -r requirements.txt

# Start the application (uses SQLite)
./startup.sh
```

**What happens:**

- ✅ Creates a local `sleeper_local.db` SQLite file
- ✅ No database installation required
- ✅ Perfect for development and testing
- ✅ Uses Gunicorn for production-ready performance

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
- Local development can use either database

## Interactive API Documentation

The application now includes **built-in interactive API documentation** powered by Swagger/OpenAPI:

- **📖 Interactive Documentation**: Visit `http://localhost:5000/docs/` to explore and test all API endpoints directly in your browser
- **🏠 Auto-redirect**: The root URL `http://localhost:5000/` automatically redirects to the documentation
- **📄 OpenAPI Spec**: Machine-readable specification available at `http://localhost:5000/openapi.json`

**Benefits of Interactive Documentation:**

- ✅ Test all endpoints directly from the web interface
- ✅ View detailed request/response schemas
- ✅ No need to remember curl syntax
- ✅ Real-time API validation and examples

## Using the API

You can use the API in two ways:

### Option 1: Interactive Documentation (Recommended)

Visit `http://localhost:5000/docs/` in your browser to test endpoints interactively.

### Option 2: Command Line (Advanced Users)

#### 1. Check Health

```bash
curl http://localhost:5000/api/ktc/health
```

#### 2. Load Rankings Data

```bash
# Superflex redraft rankings
curl -X POST "http://localhost:5000/api/ktc/refresh?league_format=superflex&is_redraft=true&tep_level=tep"

# 1QB dynasty rankings
curl -X POST "http://localhost:5000/api/ktc/refresh?league_format=1qb&is_redraft=false&tep_level=tep"
```

#### 3. Get Rankings

```bash
# Get the rankings you just loaded
curl "http://localhost:5000/api/ktc/rankings?league_format=superflex&is_redraft=true&tep_level=tep"
```

## Available Scripts

| Script | Purpose |
|--------|---------|
| `docker-compose.sh` | Manage Docker containers with PostgreSQL (up, down, logs, status, clean) |
| `startup.sh` | Start Flask application locally with SQLite |
| `run_tests.sh`
