# Test Organization

This directory contains all tests for the Sleeper Backend API, organized by type and functionality.

## 📁 Directory Structure

```
tests/
├── conftest.py              # Pytest configuration and shared fixtures
├── fixtures/                # Shared test fixtures and utilities
│   ├── database.py          # Database fixtures (client, app_context)
│   └── players.py           # Player data fixtures
├── api/                     # API endpoint tests
│   ├── test_health.py       # Health check endpoint tests
│   ├── ktc/                 # KTC API tests
│   │   ├── test_rankings.py # KTC rankings endpoint tests
│   │   └── test_bulk.py     # KTC bulk operations tests
│   └── sleeper/             # Sleeper API tests
│       ├── test_players.py  # Sleeper player endpoint tests
│       ├── test_leagues.py  # Sleeper league endpoint tests
│       ├── test_research.py # Sleeper research endpoint tests
│       └── test_stats.py    # Sleeper stats endpoint tests
├── unit/                    # Unit tests for individual modules
│   ├── models/              # Model tests
│   │   ├── test_player.py   # Player model tests
│   │   └── test_sleeper_models.py # Sleeper models tests
│   ├── managers/            # Manager tests (future)
│   ├── scrapers/            # Scraper tests (future)
│   └── utils/               # Utility tests (future)
└── integration/             # Integration tests
    ├── test_sleeper_data_saving.py # Sleeper data integration tests
    └── test_weekly_stats_api.py    # Weekly stats integration tests
```

## 🏃‍♂️ Running Tests

### Docker (Recommended)

```bash
# Run all tests
./run_tests.sh

# Run specific test categories
./run_tests.sh tests/unit/
./run_tests.sh tests/api/
./run_tests.sh tests/integration/

# Run tests with markers
./run_tests.sh -m unit
./run_tests.sh -m api
./run_tests.sh -m integration
```

### Local Development

```bash
# Run all tests locally
./run_tests_local.sh

# Run specific test files
python -m pytest tests/api/ktc/test_rankings.py -v

# Run with coverage
python -m pytest tests/ --cov=. --cov-report=html
```

## 🏷️ Test Markers

Tests are automatically marked based on their location:

- **`unit`**: Tests in `tests/unit/` - Fast, isolated tests
- **`api`**: Tests in `tests/api/` - API endpoint tests
- **`integration`**: Tests in `tests/integration/` - End-to-end tests

### Running Specific Markers

```bash
# Run only unit tests
pytest -m unit

# Run only API tests
pytest -m api

# Run only integration tests
pytest -m integration
```

## 🧪 Test Types

### Unit Tests (`tests/unit/`)

- Test individual functions, classes, and modules in isolation
- Fast execution (< 1 second per test)
- Mock external dependencies
- Focus on business logic

### API Tests (`tests/api/`)

- Test API endpoints and HTTP responses
- Use test client with in-memory database
- Verify request/response formats
- Test parameter validation

### Integration Tests (`tests/integration/`)

- Test complete workflows end-to-end
- May use external services (in test mode)
- Verify data flow between components
- Test database operations

## 🛠️ Fixtures

### Database Fixtures

- **`client`**: Flask test client with in-memory database
- **`app_context`**: Application context for database operations

### Data Fixtures

- **`sample_player`**: Sample player in database
- **`sample_player_data`**: Player data dictionary
- **`mock_sleeper_players`**: Mock Sleeper API data
- **`mock_league_data`**: Mock league data
- **`mock_weekly_stats`**: Mock weekly stats data

## 📝 Writing Tests

### Test Naming Convention

- File names: `test_*.py`
- Function names: `test_*`
- Class names: `Test*`

### Example Unit Test

```python
def test_player_model_creation(app_context):
    \"\"\"Test Player model creation.\"\"\"
    player = PlayerModel(
        player_name="Test Player",
        position="QB",
        team="TEST"
    )
    db.session.add(player)
    db.session.commit()
    
    assert player.player_name == "Test Player"
```

### Example API Test

```python
def test_health_endpoint(client):
    \"\"\"Test health check endpoint.\"\"\"
    response = client.get('/api/ktc/health')
    assert response.status_code == 200
    
    data = json.loads(response.data)
    assert 'status' in data
    assert data['status'] == 'healthy'
```

## 🔧 Configuration

### pytest.ini

- Test discovery configuration
- Markers definition
- Output formatting
- Warning filters

### conftest.py

- Shared fixtures
- Pytest hooks
- Automatic marker assignment
- Test environment setup

## 📊 Coverage

To run tests with coverage reporting:

```bash
# Install coverage
pip install coverage pytest-cov

# Run with coverage
pytest --cov=. --cov-report=html --cov-report=term-missing

# View HTML report
open htmlcov/index.html
```

## 🚨 Troubleshooting

### Common Issues

1. **Database errors**: Ensure `TEST_DATABASE_URI` is set to `sqlite:///:memory:`
2. **Import errors**: Make sure you're running from the project root
3. **Fixture not found**: Check that fixtures are imported in `conftest.py`

### Debug Mode

```bash
# Run with debug output
pytest -v -s tests/api/test_health.py

# Drop into debugger on failure
pytest --pdb tests/api/test_health.py
```

## 📋 Test Coverage

The test suite provides comprehensive coverage across all API endpoints and core functionality:

- **API Tests**: All 13 endpoints tested with various scenarios
- **Unit Tests**: Model validation and business logic  
- **Integration Tests**: End-to-end workflows and data operations

All functionality is thoroughly tested while maintaining good organization and maintainability.
