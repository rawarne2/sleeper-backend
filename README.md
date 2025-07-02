# Sleeper Backend API

A Flask-based API for scraping and serving fantasy football player rankings from KeepTradeCut (KTC).

## Features

- **Player Rankings**: Scrape dynasty and redraft player rankings from KTC
- **Multiple Formats**: Support for 1QB and Superflex league formats
- **TEP Support**: Tight End Premium scoring for dynasty leagues (TEP+, TEP++, TEP+++)
- **Database Storage**: PostgreSQL database for persistent data storage
- **JSON Export**: Save rankings to JSON files locally and optionally upload to S3
- **Health Monitoring**: Built-in health check endpoints
- **Docker Support**: Containerized deployment with Docker Compose

## Quick Start

### Using Docker Compose (Recommended)

```bash
# Clone the repository
git clone <repository-url>
cd sleeper-backend

# Set up environment variables (optional)
cp .env.example .env  # Edit with your settings

# Start the application and database
docker-compose up -d

# Check application health
curl http://localhost:5000/api/ktc/health

# Load initial data
curl -X POST "http://localhost:5000/api/ktc/refresh?league_format=superflex&is_redraft=false&tep_level=tep"
```

### Manual Setup

```bash
# Clone the repository
git clone <repository-url>
cd sleeper-backend

# Install Python dependencies
pip install -r requirements.txt

# Set up PostgreSQL databases
python setup_postgres.py

# Start the application
python app.py
```

## API Endpoints

### Health Check

```bash
GET /api/ktc/health
```

### Refresh Rankings

```bash
POST /api/ktc/refresh?league_format={format}&is_redraft={boolean}&tep_level={tep}
```

**Parameters:**

- `league_format`: `1qb` or `superflex`
- `is_redraft`: `true` or `false`
- `tep_level`: `tep`, `tepp`, `teppp` (dynasty only)

### Get Rankings

```bash
GET /api/ktc/rankings?league_format={format}&is_redraft={boolean}&tep_level={tep}
```

### Database Cleanup

```bash
POST /api/ktc/cleanup?league_format={format}&is_redraft={boolean}&tep_level={tep}
```

## Configuration

### Environment Variables

Create a `.env` file in the root directory:

```bash
# Database Configuration
DATABASE_URL=postgresql://postgres:password@localhost:5433/sleeper_db

# AWS S3 Configuration (optional)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_DEFAULT_REGION=us-east-1
S3_BUCKET=your-bucket-name

# Flask Configuration
FLASK_ENV=development
```

### Database Configuration

The application uses PostgreSQL with the following default settings:

- Host: `localhost`
- Port: `5433` (Docker), `5432` (local)
- Database: `sleeper_db`
- Test Database: `sleeper_test_db`
- Username: `postgres`
- Password: `password`

## Development

### Local Development Setup

```bash
# Clone repository
git clone <repository-url>
cd sleeper-backend

# Set up Python environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start PostgreSQL (using Docker)
docker-compose up postgres -d

# Start the application
python app.py
```

### Running Tests

```bash
# Run all tests
python -m pytest

# Run specific test file
python -m pytest unit_tests.py -v

# Run with coverage
python -m pytest --cov=app tests/
```

### Database Management

```bash
# Initialize database tables
flask init_db

# Set up PostgreSQL databases
python setup_postgres.py
```

## Docker Deployment

### Using Docker Compose

```bash
# Build and start all services
docker-compose up --build

# Start in background
docker-compose up -d

# View logs
docker-compose logs -f sleeper-backend

# Stop services
docker-compose down

# Clean up volumes (removes database data)
docker-compose down -v
```

### Using Docker Only

```bash
# Build the image
docker build -t sleeper-backend .

# Run with external PostgreSQL
docker run -d \
  --name sleeper-backend \
  -p 5000:5000 \
  -e DATABASE_URL=postgresql://user:pass@host:port/db \
  sleeper-backend
```

## API Usage Examples

### Dynasty Rankings

```bash
# Get Superflex Dynasty TEP+ rankings
curl "http://localhost:5000/api/ktc/rankings?league_format=superflex&is_redraft=false&tep_level=tep"

# Refresh 1QB Dynasty base rankings
curl -X POST "http://localhost:5000/api/ktc/refresh?league_format=1qb&is_redraft=false&tep_level=tep"
```

### Redraft Rankings

```bash
# Get Superflex redraft rankings
curl "http://localhost:5000/api/ktc/rankings?league_format=superflex&is_redraft=true"

# Refresh 1QB redraft rankings
curl -X POST "http://localhost:5000/api/ktc/refresh?league_format=1qb&is_redraft=true"
```

## Data Storage

### Local Files

- JSON exports saved to `./data-files/` directory
- **Standard naming**: `ktc_{league_format}_{format_type}_{tep_level}_{timestamp}.json`
- **Descriptive naming**: `ktc_{operation}_{league_format}_{format_type}_{tep_level}_{timestamp}.json`
- **Human-readable naming**: `KTC {Operation} - {League} {Format} {TEP} - {Timestamp}.json`

**Examples:**

- `ktc_superflex_dynasty_tep_20241201_143022.json`
- `ktc_refresh_superflex_dynasty_tep_20241201_143022.json`
- `KTC Refresh - Superflex Dynasty tep - 2024-12-01 14-30-22.json`

**TEP Level Usage:**

- `tep` → `tep`
- `tepp` → `tepp`
- `teppp` → `teppp`
- `None` → `no_tep`

### S3 Upload

- Configurable via environment variables
- Automatic upload after successful scraping
- File naming matches local exports

### Filename Generation

The application provides three different filename generation methods:

1. **`create_json_filename()`** - Standard naming with prefix support
2. **`create_descriptive_filename()`** - Enhanced naming with operation type and optional timestamps
3. **`create_human_readable_filename()`** - User-friendly naming with spaces and proper formatting

All methods support:

- League format detection (1QB/Superflex)
- Format type (Dynasty/Redraft)
- TEP level usage (tep/tepp/teppp/no_tep)
- Timestamp inclusion for uniqueness

### Database

- PostgreSQL with connection pooling
- Automatic cleanup of incomplete data
- Index optimization for query performance

## Troubleshooting

### Common Issues

1. **Port 5432 already in use**
   - The docker-compose uses port 5433 to avoid conflicts
   - Update `DATABASE_URL` if needed

2. **Database connection errors**
   - Ensure PostgreSQL is running
   - Check connection parameters
   - Verify database exists

3. **Scraping failures**
   - Check internet connection
   - Verify KTC website accessibility
   - Review application logs

### Database Issues

```bash
# Check database connection
curl http://localhost:5000/api/ktc/health

# Clean up incomplete data
curl -X POST "http://localhost:5000/api/ktc/cleanup?league_format=superflex&is_redraft=false"

# Recreate database tables
flask init_db
```

### Docker Issues

```bash
# Rebuild containers
docker-compose up --build --force-recreate

# Check container logs
docker-compose logs sleeper-backend
docker-compose logs postgres

# Reset database volume
docker-compose down -v
docker-compose up -d
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run the test suite
6. Submit a pull request

## Architecture

```
sleeper-backend/
├── app.py               # Main Flask application
├── requirements.txt     # Python dependencies
├── Dockerfile          # Container configuration
├── docker-compose.yml  # Multi-container setup
├── startup.sh          # Container startup script
├── setup_postgres.py   # Database setup utility
├── data-files/         # JSON export directory
├── tests/              # Test suite
│   ├── unit_tests.py
│   ├── test_ktc_api.py
│   └── test_ktc_simple.py
└── README.md           # This file
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.
