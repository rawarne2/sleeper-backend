# Sleeper Backend - KTC API

A Flask API for scraping and serving KeepTradeCut fantasy football rankings.

## Quick Start

### Prerequisites

- Docker and Docker Compose installed on your system

### Run the App

#### Option 1: Using Docker Compose (Recommended)

```sh
# Start the application with persistent database
./docker-compose.sh up

# Or use docker-compose directly
docker-compose up -d
```

#### Option 2: Using Docker directly

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
| `./docker-compose.sh up` | Start the app with Docker Compose and persistent database |
| `./docker-compose.sh down` | Stop the Docker Compose application |
| `./docker-compose.sh rebuild` | Rebuild and restart the application |
| `./docker-compose.sh logs` | View application logs |
| `./docker-compose.sh status` | Check container and volume status |
| `./run_app.sh` | Build and run the Flask API in Docker (alternative method) |
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

- **S3 Upload**: The app includes S3 upload functionality but it's not needed for basic usage. See [S3 Configuration](#s3-configuration) section below for setup instructions.
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

## Data Persistence

### Database Persistence

The application uses SQLite database that persists data between container restarts:

#### Docker Compose (Recommended)

- **Database**: Stored in a Docker volume `database_data` that persists between container restarts
- **Data files**: Stored in a Docker volume `data_files` for JSON export files
- **Automatic**: No manual volume mounting needed - Docker Compose handles everything

#### Direct Docker

- **Database**: Mounted to `./instance/` directory on host
- **Data files**: Mounted to `./data-files/` directory on host

### JSON Data Files

When you use the `/api/ktc/refresh` endpoint, the scraped data is saved to JSON files that persist:

- **Docker Compose**: Files saved to `data_files` volume
- **Local development**: Files saved to `./data-files/`
- **Direct Docker**: Files saved to `/app/data-files/` (mounted to `./data-files/` on host)

#### File naming convention

- `ktc_refresh_{league_format}_{dynasty/redraft}_tep{tep_value}.json`
- Examples:
  - `ktc_refresh_1qb_dynasty_tep0.json`
  - `ktc_refresh_sf_redraft_tep2.json`

#### Volume Information

Check volume status with:

```bash
./docker-compose.sh status
```

Or directly with Docker:

```bash
docker volume ls
docker volume inspect sleeper-backend_database_data
```

## Docker Setup

### Quick Start

The application is now configured with a simplified Docker setup:

```bash
# Start the application
./docker-compose.sh up

# View logs
./docker-compose.sh logs

# Stop the application
./docker-compose.sh down

# Clean up (remove containers)
./docker-compose.sh clean
```

The application will be available at: <http://localhost:5000>
Health check: <http://localhost:5000/api/ktc/health>

## S3 Configuration

The application includes optional S3 upload functionality for storing JSON data files. To enable S3 uploads in Docker:

### Method 1: Environment Variables (Recommended)

1. Copy the provided `.env.example` file to `.env`:

   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and add your AWS credentials:

   ```bash
   AWS_ACCESS_KEY_ID=your_access_key_here
   AWS_SECRET_ACCESS_KEY=your_secret_key_here
   AWS_DEFAULT_REGION=us-east-1
   S3_BUCKET=your-bucket-name
   ```

3. Docker Compose will automatically load these variables.

### Method 2: Mount AWS Credentials Directory

Uncomment the AWS credentials volume mount in `docker-compose.yml`:

```yaml
volumes:
  # ... other volumes ...
  - ~/.aws:/root/.aws:ro  # Uncomment this line
```

### Method 3: Set Environment Variables Directly

Export the variables in your shell before running Docker Compose:

```bash
export AWS_ACCESS_KEY_ID=your_access_key_here
export AWS_SECRET_ACCESS_KEY=your_secret_key_here
export AWS_DEFAULT_REGION=us-east-1
export S3_BUCKET=your-bucket-name
./docker-compose.sh up
```

### Why S3 Upload Fails in Docker but Works Locally

When running locally, boto3 can find AWS credentials from:

- Your `~/.aws/credentials` file
- Environment variables in your shell
- AWS CLI configuration

In Docker containers, these credentials aren't available unless explicitly provided through one of the methods above.

### Directory Structure

```
sleeper-backend/
├── instance/           # SQLite database storage
│   └── db.sqlite      # Database file (local & mounted to container)
├── data-files/        # JSON data files (mounted to container)
├── docker-compose.yml # Docker configuration
├── docker-compose.sh  # Helper script
├── Dockerfile        # Container definition
└── app.py            # Main application
```

### How it works

- **Database**: SQLite database stored in `instance/db.sqlite`
- **Volume Mounts**: Local directories are mounted to container for persistence
- **No Docker Volumes**: Uses local directory mounts instead of Docker volumes
- **Development Ready**: Changes to local files are reflected in container
