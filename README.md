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

- run `./run_app.sh` to start the app and then run the following commands in a new terminal to test the API, or use Insomnia or Postman.

### Using API Testing Tools

For easier API testing, you can use **Postman** or **Insomnia** instead of curl commands:

- **Base URL**: `http://localhost:5000`
- **Content-Type**: `application/json` (for POST requests)

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

All endpoints support the following query parameters:

- `is_redraft`: `true` or `false` (default: `false`) - Fantasy/redraft vs dynasty league type
- `league_format`: `1QB` or `SF` (default: `1QB`) - Single QB vs Superflex scoring
- `tep`: `0`, `1`, `2`, or `3` (default: `0`) - Tight End Premium scoring level

## Testing TE Values Across League Types

To ensure TE (Tight End) values are correctly saved and calculated for different league configurations, test the key scenarios and compare values from the curl output, database, or CSV with the corresponding KTC URL. Modify or remove `| jq '.players[:100]` to get more or less data returned.

### Test Different TEP (Tight End Premium) Levels

```sh
# TEP 0 (No TE Premium) - Dynasty SF
curl -X POST "http://localhost:5000/api/ktc/refresh?is_redraft=false&league_format=SF&tep=0"
curl "http://localhost:5000/api/ktc/rankings?is_redraft=false&league_format=SF&tep=0" | jq '.players[:100]'

# TEP 1 (TE+) - Dynasty SF
curl -X POST "http://localhost:5000/api/ktc/refresh?is_redraft=false&league_format=SF&tep=1"
curl "http://localhost:5000/api/ktc/rankings?is_redraft=false&league_format=SF&tep=1" | jq '.players[:100]'

# TEP 2 (TE++) - Dynasty SF
curl -X POST "http://localhost:5000/api/ktc/refresh?is_redraft=false&league_format=SF&tep=2"
curl "http://localhost:5000/api/ktc/rankings?is_redraft=false&league_format=SF&tep=2" | jq '.players[:100]'

# TEP 3 (TE+++) - Dynasty SF
curl -X POST "http://localhost:5000/api/ktc/refresh?is_redraft=false&league_format=SF&tep=3"
curl "http://localhost:5000/api/ktc/rankings?is_redraft=false&league_format=SF&tep=3" | jq '.players[:100]'
```

### Test League Formats and Types

```sh
# Dynasty 1QB with TEP 1
curl -X POST "http://localhost:5000/api/ktc/refresh?is_redraft=false&league_format=1QB&tep=1"
curl "http://localhost:5000/api/ktc/rankings?is_redraft=false&league_format=1QB&tep=1" | jq '.players[:100]'

# Dynasty SF with TEP 1
curl -X POST "http://localhost:5000/api/ktc/refresh?is_redraft=false&league_format=SF&tep=1"
curl "http://localhost:5000/api/ktc/rankings?is_redraft=false&league_format=SF&tep=1" | jq '.players[:100]'

# Redraft SF (TEP not applicable)
curl -X POST "http://localhost:5000/api/ktc/refresh?is_redraft=true&league_format=SF&tep=0"
curl "http://localhost:5000/api/ktc/rankings?is_redraft=true&league_format=SF&tep=0" | jq '.players[:100]'
```

### Validation Steps

1. **Compare TE values across TEP levels** - Higher TEP should increase TE values
2. **Verify data consistency** - Multiple API calls should return identical data
3. **Cross-reference with KTC** - Compare your results with the corresponding KTC URLs:
   - Dynasty SF: `https://keeptradecut.com/dynasty-rankings?format=0&sf=true&tep=X`
   - Dynasty 1QB: `https://keeptradecut.com/dynasty-rankings?format=1&sf=true&tep=X`
   - Redraft SF: `https://keeptradecut.com/fantasy-rankings?format=0`
4. **Run automated tests**: `./run_tests.sh`

**Expected Results**: TE values should increase with higher TEP levels, differ between league formats, and match the corresponding KTC website data.

## Standalone Scraper Script

The `ktc-scrape.py` script can be used independently to scrape KTC data and export to CSV:

```sh
python ktc-scrape.py
```

The script will prompt you for:

- League type (redraft/fantasy vs dynasty)
- League format (1QB vs Superflex)  
- TEP level (0-3, dynasty only in this project, but exists for redraft/fantasy in KTC)
- S3 upload preference (optional)

The script outputs a `ktc.csv` file with the scraped rankings data. This is useful for one-off data exports or integrating KTC data into other workflows.

## Notes

- **S3 Upload**: The app includes S3 upload functionality but it's not needed for basic usage. The `S3_BUCKET` environment variable is not needed for this project to work.
- **Database**: Uses SQLite database that's automatically initialized in the Docker container.
- **Docker**: The app runs in a containerized environment with Python 3.13 and includes a virtual environment for dependency isolation.
- **TEP Impact**: TEP only applies to dynasty leagues in this project; redraft leagues ignore TEP settings. TEP is available for redraft/fantasy in KTC, but not yet implemented in this project.

## Local Development (Without Docker)

If needed, you can run locally:

```sh
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
flask init_db
python app.py
```

## Key terms

- `tep`: Tight End Premium scoring (0=None, 1=TE+, 2=TE++, 3=TE+++)
- `sf`: Superflex scoring format (allows starting 2 QBs)
- `redraft`/`fantasy`: Redraft Fantasy Football (same thing) - league resets each year
- `dynasty`: Dynasty Football - keep players across multiple seasons
- `1QB`: Traditional single quarterback league format

**Note**: Redraft and fantasy football are the same thing. Both redraft/fantasy and dynasty leagues can use 1QB or Superflex formats, and both can have TEP levels (though TEP for redraft/fantasy is not yet implemented in the API or script).
