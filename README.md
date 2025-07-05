# Sleeper Backend API

A Flask-based API for scraping and serving fantasy football player rankings from KeepTradeCut (KTC).

## Features

- **Player Rankings**: Scrape dynasty and redraft player rankings from KTC
- **Multiple Formats**: Support for 1QB and Superflex league formats  
- **TEP Support**: Tight End Premium scoring (tep, tepp, teppp)
- **Database Storage**: PostgreSQL database with Docker support

## Quick Start

### Using Docker (Recommended)

Use the provided `docker-compose.sh` script to manage the application:

```bash
# Start the application
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

### Manual Setup

If you prefer to run without Docker:

```bash
# Install dependencies
pip install -r requirements.txt

# Set up PostgreSQL databases
python setup_postgres.py

# Start the application
./startup.sh
```

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
| `docker-compose.sh` | Manage Docker containers (up, down, logs, status, clean) |
| `startup.sh` | Initialize database and start Flask application |
| `run_tests.sh` | Run the test suite |
| `setup_postgres.py` | Set up PostgreSQL databases for local development |

## API Parameters

**League Format:**

- `1qb` - Standard 1 quarterback leagues (only 1 QB can be started)
- `superflex` - Superflex/2QB leagues (can start 2 QBs or 1 QB + flex player)

*Note: Superflex leagues heavily favor QBs since you can start 2, making QB values much higher than in 1QB leagues.*

**Ranking Type:**

- `is_redraft=true` - Redraft/seasonal rankings (draft new team each year)
- `is_redraft=false` - Dynasty/keeper rankings (keep players long-term)

*Note: Dynasty values focus on long-term potential and age, while redraft focuses on current season performance.*

**TEP Level:**

- `tep` - Tight End Premium (about +0.5 points per reception)
- `tepp` - Tight End Premium Plus (about +1.0 points per reception)  
- `teppp` - Tight End Premium Plus Plus (about +1.5 points per reception)
- Leave empty for standard scoring

*Note: TEP makes tight ends more valuable since they get bonus points. Only applies to dynasty rankings.*

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
# Quick start
./docker-compose.sh up

# Load superflex redraft data
curl -X POST "http://localhost:5000/api/ktc/refresh?league_format=superflex&is_redraft=true&tep_level=tep"

# Get rankings
curl "http://localhost:5000/api/ktc/rankings?league_format=superflex&is_redraft=true&tep_level=tep"

# Check logs
./docker-compose.sh logs

# Stop everything
./docker-compose.sh down
```

## Troubleshooting

- **Database issues**: Try `./docker-compose.sh clean` then `./docker-compose.sh up`
- **Empty rankings**: Call the `/refresh` endpoint first to populate data
- **Script permissions**: Run `chmod +x docker-compose.sh startup.sh run_tests.sh`

## Development

Run tests with the test script:

```bash
./run_tests.sh
```

For development without Docker:

```bash
python setup_postgres.py  # Set up databases
./startup.sh              # Start application
```
