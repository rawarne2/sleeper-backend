#!/bin/sh
docker build -t sleeper-backend .
docker run --rm -e TEST_DATABASE_URI='sqlite:///:memory:' sleeper-backend pytest -v ${@}