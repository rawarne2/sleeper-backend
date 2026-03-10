#!/bin/sh

# Local Test Runner (without Docker)
# 
# This script runs tests locally using the new organized test structure.
# Requires pytest to be installed in your environment.
# 
# Usage:
#   ./run_tests_local.sh                    # Run all tests
#   ./run_tests_local.sh tests/unit/        # Run only unit tests
#   ./run_tests_local.sh tests/api/         # Run only API tests
#   ./run_tests_local.sh tests/integration/ # Run only integration tests
#   ./run_tests_local.sh -m unit            # Run tests marked as unit tests
#   ./run_tests_local.sh -m api             # Run tests marked as API tests
#   ./run_tests_local.sh -m integration     # Run tests marked as integration tests

# Set test environment
export TEST_DATABASE_URI='sqlite:///:memory:'

echo "🧪 Running tests locally..."

# Run tests with organized structure
python -m pytest tests/ -v --tb=short ${@}

echo "✅ Local test run completed!"
