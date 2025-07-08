#!/bin/bash

# Docker Compose helper script for sleeper-backend

set -e

show_help() {
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  up          Start the application"
    echo "  down        Stop the application"
    echo "  restart     Restart the application"
    echo "  logs        Show application logs"
    echo "  status      Show container status"
    echo "  clean       Stop and remove containers"
    echo "  help        Show this help message"
    echo ""
    echo "The application will be available at http://localhost:5000"
    echo "Health check endpoint: http://localhost:5000/api/ktc/health"
}

case "$1" in
    up)
        echo "Starting sleeper-backend..."
        docker-compose up -d --build
        echo "✅ Application started at http://localhost:5000"
        ;;
    down)
        echo "Stopping sleeper-backend..."
        docker-compose down
        ;;
    restart)
        echo "Restarting sleeper-backend..."
        docker-compose restart
        ;;
    logs)
        docker-compose logs -f sleeper-backend
        ;;
    status)
        docker-compose ps
        ;;
    clean)
        echo "Cleaning up..."
        docker-compose down -v
        docker system prune -f
        echo "✅ Cleanup complete"
        ;;
    help|--help|-h)
        show_help
        ;;
    "")
        echo "No command specified."
        show_help
        exit 1
        ;;
    *)
        echo "Unknown command: $1"
        show_help
        exit 1
        ;;
esac 