#!/bin/sh

# Sleeper Backend Test Runner
# 
# This script runs tests using the new organized test structure.
# 
# Usage:
#   ./run_tests.sh                    # Run all tests
#   ./run_tests.sh tests/unit/        # Run only unit tests
#   ./run_tests.sh tests/api/         # Run only API tests
#   ./run_tests.sh tests/integration/ # Run only integration tests
#   ./run_tests.sh -m unit            # Run tests marked as unit tests
#   ./run_tests.sh -m api             # Run tests marked as API tests
#   ./run_tests.sh -m integration     # Run tests marked as integration tests

# Build the Docker image
echo "🏗️  Building Docker image..."
docker build -t sleeper-backend .

# Run tests with organized structure
echo "🧪 Running tests..."
docker run --rm \
    -e TEST_DATABASE_URI='sqlite:///:memory:' \
    sleeper-backend \
    pytest tests/ -v --tb=short ${@}

echo "✅ Test run completed!"