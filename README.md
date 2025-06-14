# Sleeper Backend - KTC API

A Flask API for scraping and serving KeepTradeCut fantasy football rankings.

## Quick Start

### Prerequisites

- Docker installed on your system

### Run the App

```sh
./run_app.sh
```

The API will be available at `http://localhost:5000`

### Run Tests

```sh
./run_tests.sh
```

## Available Scripts

| Script | Description |
|--------|-------------|
| `./run_app.sh` | Build and run the Flask API in Docker |
| `./run_tests.sh` | Build and run the test suite in Docker |
| `./build_docker.sh` | Build the Docker image (used by other scripts) |

## API Endpoints

### Refresh Rankings

Scrape fresh data from KeepTradeCut and store in database:

```sh
curl -X POST "http://localhost:5000/api/ktc/refresh?is_redraft=false&league_format=SF&tep=1"
```

### Get Rankings

Retrieve stored rankings from database:

```sh
curl "http://localhost:5000/api/ktc/rankings?is_redraft=false&league_format=SF&tep=1"
```

## Parameters

- `is_redraft`: `true` or `false` (default: `false`)
- `league_format`: `1QB` or `SF` (default: `1QB`)
- `tep`: `0`, `1`, `2`, or `3` (default: `0`) - Tight End Premium scoring

## Notes

- **S3 Upload**: The app includes S3 upload functionality but it's not needed for basic usage. The `S3_BUCKET` environment variable is not needed for this project to work.
- **Database**: Uses SQLite database that's automatically initialized in the Docker container.
- **Docker**: The app runs in a containerized environment with Python 3.13 and includes a virtual environment for dependency isolation.

## Local Development (Without Docker)

If needed, you can run locally:

```sh
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
flask init_db
python app.py
```

## Key terms to know

- `tep`: Tight End Premium scoring
- `sf`: Superflex scoring
- `rdrft`: Redraft scoring
- `dynasty`: Dynasty Football scoring
- `fantasy`: Fantasy Foootball scoring
