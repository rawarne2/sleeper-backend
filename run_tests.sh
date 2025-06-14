#!/bin/sh
./build_docker.sh sleeper-backend
docker run --rm sleeper-backend pytest unit_tests.py -v ${@}