#!/bin/sh
docker build -t sleeper-backend .
docker run --rm sleeper-backend pytest unit_tests.py -v ${@}