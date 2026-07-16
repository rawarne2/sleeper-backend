#!/usr/bin/env python
"""
Setup script for PostgreSQL database initialization.
Run this script to create the necessary databases for the application.
"""

import os
import sys
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


def create_database(host, port, user, password, db_name):
    """Create a PostgreSQL database if it doesn't exist"""
    try:
        # Connect to PostgreSQL server (to the default 'postgres' database)
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database='postgres'
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

        # Check if database exists
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT 1 FROM pg_database WHERE datname = '{db_name}'")
        exists = cursor.fetchone()

        if not exists:
            cursor.execute(f'CREATE DATABASE "{db_name}"')
            print(f"✅ Created database: {db_name}")
        else:
            print(f"ℹ️  Database already exists: {db_name}")

        cursor.close()
        conn.close()
        return True

    except Exception as e:
        print(f"❌ Error creating database {db_name}: {e}")
        return False


def setup_databases():
    """Setup both main and test databases"""

    # Database configuration - can be overridden with environment variables
    host = os.getenv('POSTGRES_HOST', 'localhost')
    port = os.getenv('POSTGRES_PORT', '5433')
    user = os.getenv('POSTGRES_USER', 'postgres')
    password = os.getenv('POSTGRES_PASSWORD', 'password')

    # Database names
    main_db = 'sleeper_db'
    test_db = 'sleeper_test_db'

    print("🔄 Setting up PostgreSQL databases...")
    print(f"Host: {host}:{port}")
    print(f"User: {user}")
    print()

    # Create main database
    if create_database(host, port, user, password, main_db):
        print(f"✅ Main database setup complete: {main_db}")
    else:
        print(f"❌ Failed to setup main database: {main_db}")
        return False

    # Create test database
    if create_database(host, port, user, password, test_db):
        print(f"✅ Test database setup complete: {test_db}")
    else:
        print(f"❌ Failed to setup test database: {test_db}")
        return False

    print()
    print("🎉 Database setup completed successfully!")
    print()
    print("Next steps:")
    print("1. Start your application: ./startup.sh (or python app.py)")
    print("2. Or use Docker: ./docker-compose.sh up")

    return True


if __name__ == "__main__":
    if not setup_databases():
        sys.exit(1)
