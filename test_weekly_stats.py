#!/usr/bin/env python3
"""
Test script for weekly stats functionality.

This script tests the new weekly stats endpoints and database operations
to ensure they work correctly with the Sleeper API.
"""

import requests
import json
from datetime import datetime

# Configuration
import os
BASE_URL = os.getenv("BASE_URL", "http://localhost:5000/api")
LEAGUE_ID = "1050831680350568448"  # Your 2024 league ID
SEASON = "2024"
WEEK = 1


def test_seed_league_stats():
    """Test seeding league stats information."""
    print("Testing seed league stats...")

    url = f"{BASE_URL}/sleeper/league/{LEAGUE_ID}/stats/seed"
    data = {
        'league_name': 'Test Fantasy League',
        'season': SEASON,
    }

    response = requests.post(url, json=data)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    print()


def test_refresh_weekly_stats():
    """Test refreshing weekly stats for a specific week."""
    print("Testing refresh weekly stats...")

    url = f"{BASE_URL}/sleeper/league/{LEAGUE_ID}/stats/week/{WEEK}/refresh"
    params = {
        'season': SEASON,
        'league_type': 'dynasty'
    }

    response = requests.post(url, params=params)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    print()


def test_get_weekly_stats():
    """Test getting weekly stats for a specific week."""
    print("Testing get weekly stats...")

    url = f"{BASE_URL}/sleeper/league/{LEAGUE_ID}/stats/week/{WEEK}"
    params = {
        'season': SEASON,
        'league_type': 'dynasty'
    }

    response = requests.get(url, params=params)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    print()


def test_get_weekly_stats_average():
    """Test getting weekly stats with average calculation."""
    print("Testing get weekly stats with average...")

    url = f"{BASE_URL}/sleeper/league/{LEAGUE_ID}/stats/week/{WEEK}"
    params = {
        'season': SEASON,
        'league_type': 2,
        'average': 'true'
    }

    response = requests.get(url, params=params)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    print()


def test_health_check():
    """Test API health check."""
    print("Testing API health check...")

    url = f"{BASE_URL}/ktc/health"
    response = requests.get(url)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    print()


def main():
    """Run all tests."""
    print("=" * 60)
    print("Weekly Stats Functionality Test")
    print("=" * 60)
    print(f"Base URL: {BASE_URL}")
    print(f"League ID: {LEAGUE_ID}")
    print(f"Season: {SEASON}")
    print(f"Week: {WEEK}")
    print(f"Timestamp: {datetime.now()}")
    print()

    try:
        # Test health check first
        test_health_check()

        # Test weekly stats functionality
        test_seed_league_stats()
        test_refresh_weekly_stats()
        test_get_weekly_stats()
        test_get_weekly_stats_average()

        print("=" * 60)
        print("All tests completed!")
        print("=" * 60)

    except Exception as e:
        print(f"Error during testing: {e}")
        print("Make sure the server is running and accessible.")


if __name__ == "__main__":
    main()
