# Sleeper Backend API

A Flask-based API for scraping and serving fantasy football player rankings from KeepTradeCut (KTC).

## Features

- **Player Rankings**: Scrape dynasty and redraft player rankings from KTC
- **Multiple Formats**: Support for 1QB and Superflex league formats  
- **TEP Support**: Tight End Premium scoring (tep, tepp, teppp)
- **Database Storage**: PostgreSQL for production/Docker, SQLite for development/testing

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

## Using the API

### 1. Check Health

```bash
curl http://localhost:5000/api/ktc/health
```

### 2. Load Rankings Data

```bash
# Superflex redraft rankings
curl -X POST "http://localhost:5000/api/ktc/refresh?league_format=superflex&is_redraft=true&tep_level=tep"

# 1QB dynasty rankings
curl -X POST "http://localhost:5000/api/ktc/refresh?league_format=1qb&is_redraft=false&tep_level=tep"
```

### 3. Get Rankings

```bash
# Get the rankings you just loaded
curl "http://localhost:5000/api/ktc/rankings?league_format=superflex&is_redraft=true&tep_level=tep"
```

## Available Scripts

| Script | Purpose |
|--------|---------|
| `docker-compose.sh` | Manage Docker containers with PostgreSQL (up, down, logs, status, clean) |
| `startup.sh` | Start Flask application locally with SQLite |
| `run_tests.sh` | Run the test suite |
| `setup_postgres.py` | Set up PostgreSQL databases (for advanced local PostgreSQL setup) |

## Setup Comparison

| Feature | Local (`./startup.sh`) | Docker (`./docker-compose.sh`) |
|---------|----------------------|-------------------------------|
| Database | **SQLite** (file-based) | **PostgreSQL** (containerized) |
| Setup | Zero setup required | Docker required |
| Performance | Fast startup | Production-ready |
| Use Case | Development/Testing | Production/Team development |
| Data Persistence | Local file | Container volume |

## API Endpoints

### KTC (KeepTradeCut) Rankings

- `POST /api/ktc/refresh` - Load fresh rankings data
- `GET /api/ktc/rankings` - Get stored rankings
- `POST /api/ktc/cleanup` - Clean up database
- `GET /api/ktc/health` - Check database health

### Sleeper API Integration

- `POST /api/sleeper/refresh` - Refresh Sleeper player data
- `GET /api/sleeper/league/{league_id}` - Get league data (info, rosters, users)
- `GET /api/sleeper/league/{league_id}/rosters` - Get league rosters only
- `GET /api/sleeper/league/{league_id}/users` - Get league users only
- `POST /api/sleeper/league/{league_id}/refresh` - Refresh specific league data
- `GET /api/sleeper/players/research/{season}` - Get player research data
- `POST /api/sleeper/players/research/{season}/refresh` - Refresh research data
- `POST /api/sleeper/refresh/all` - Refresh all data (for scheduled tasks)

## API Parameters

**League Format:**

- `1qb` - Standard 1 quarterback leagues (only 1 QB can be started)
- `superflex` - Superflex/2QB leagues (can start 2 QBs or 1 QB + flex player)

*Note: Superflex leagues heavily favor QBs since you can start 2, making QB values much higher than in 1QB leagues.*

**Ranking Type:**

- `is_redraft=true` - Redraft/fantasy rankings (draft new team each year)
- `is_redraft=false` - Dynasty rankings (keep players long-term)

*Note: Dynasty values focus on long-term potential and age, while redraft focuses only on the current season's performance.*

**TEP Level:**

- `tep` - Tight End Premium (about +0.5 points per reception)
- `tepp` - Tight End Premium Plus (about +1.0 points per reception)  
- `teppp` - Tight End Premium Plus Plus (about +1.5 points per reception)
- Leave empty for standard scoring

*Note: TEP makes tight ends more valuable since they get bonus points. Only applies to dynasty rankings. TEP values are managed by the KTC API.*

## Example API Calls

**Load Different Rankings:**

```bash
# Superflex dynasty with TEP
curl -X POST "http://localhost:5000/api/ktc/refresh?league_format=superflex&is_redraft=false&tep_level=tep"

# 1QB redraft (standard scoring)
curl -X POST "http://localhost:5000/api/ktc/refresh?league_format=1qb&is_redraft=true"

# Superflex dynasty with max TEP
curl -X POST "http://localhost:5000/api/ktc/refresh?league_format=superflex&is_redraft=false&tep_level=teppp"
```

**Get Rankings:**

```bash
# Get superflex dynasty TEP rankings
curl "http://localhost:5000/api/ktc/rankings?league_format=superflex&is_redraft=false&tep_level=tep"

# Get 1QB redraft rankings
curl "http://localhost:5000/api/ktc/rankings?league_format=1qb&is_redraft=true"

# Get superflex redraft rankings
curl "http://localhost:5000/api/ktc/rankings?league_format=superflex&is_redraft=true"
```

**Clean Up Data:**

```bash
# Clean up specific configuration
curl -X POST "http://localhost:5000/api/ktc/cleanup?league_format=superflex&is_redraft=false&tep_level=tep"
```

## Environment Variables (Optional)

Create a `.env` file for S3 uploads or custom database settings:

```bash
# Database (if not using default)
DATABASE_URL=postgresql://user:pass@host:port/database

# S3 Upload (optional)
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
S3_BUCKET=your-bucket
```

## Common Commands

```bash
# Quick start (local development)
./startup.sh

# Quick start (Docker)
./docker-compose.sh up

# Load superflex redraft data
curl -X POST "http://localhost:5000/api/ktc/refresh?league_format=superflex&is_redraft=true&tep_level=tep"

# Get rankings
curl "http://localhost:5000/api/ktc/rankings?league_format=superflex&is_redraft=true&tep_level=tep"

# Check logs (Docker)
./docker-compose.sh logs

# Stop everything
./docker-compose.sh down
```

## Troubleshooting

- **Database issues**: Try `./docker-compose.sh clean` then `./docker-compose.sh up`
- **Empty rankings**: Call the `/refresh` endpoint first to populate data
- **Script permissions**: Run `chmod +x docker-compose.sh startup.sh run_tests.sh`
- **Local development**: Use `./startup.sh` for SQLite-based development

## Development

### Running Tests

**Option 1: Direct Testing (Recommended for development)**

Run tests directly with pytest - fastest and doesn't require Docker:

```bash
# Run all tests
python -m pytest -v

# Run specific test file
python -m pytest unit_tests.py -v
python -m pytest test_ktc_api.py -v
python -m pytest test_ktc_simple.py -v
```

**Option 2: Docker-based Testing**

Run tests in a Docker container (uses SQLite for testing):

```bash
# Run all tests in Docker
./run_tests.sh

# Run specific test file in Docker
./run_tests.sh unit_tests.py -v
```

**Setting up for Development**

For local development:

```bash
# Simple setup (SQLite)
./startup.sh

# OR advanced setup (PostgreSQL)
python setup_postgres.py
export DATABASE_URL="postgresql://user:pass@localhost:5432/sleeper_db"
./startup.sh
```
