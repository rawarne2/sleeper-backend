#!/bin/sh
./build_docker.sh sleeper-backend

# Run with data refresh enabled
# Set REFRESH_DATA_ON_STARTUP=true to automatically refresh data on container startup
docker run --name sleeper-backend-container --rm -it -p 5000:5000 -v "$(pwd)/instance:/app/instance" -e REFRESH_DATA_ON_STARTUP=true sleeper-backend

# Alternative: Run without data refresh (just initialize empty database)
# docker run --name sleeper-backend-container --rm -it -p 5000:5000 -v "$(pwd)/instance:/app/instance" sleeper-backend

# To view logs in real-time from another terminal (while container is running):
# docker logs -f sleeper-backend-container

# To run in detached mode and view logs separately:
# docker run --name sleeper-backend-container -d -p 5000:5000 -v "$(pwd)/instance:/app/instance" -e REFRESH_DATA_ON_STARTUP=true sleeper-backend
# docker logs -f sleeper-backend-container 