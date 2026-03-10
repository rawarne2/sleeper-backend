#!/bin/bash

# Docker Compose helper script for sleeper-backend

set -e

if command -v docker-compose >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker-compose"
else
    DOCKER_COMPOSE="docker compose"
fi

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
    echo "The application will be available at http://localhost:5001"
    echo "📖 Interactive API documentation: http://localhost:5001/docs/"
    echo "📄 OpenAPI specification: http://localhost:5001/openapi.json"
    echo "🏥 Health check endpoint: http://localhost:5001/api/ktc/health"
}

case "$1" in
    up)
        echo "Starting sleeper-backend..."
        $DOCKER_COMPOSE up -d --build
        echo "✅ Application started at http://localhost:5001"
        ;;
    down)
        echo "Stopping sleeper-backend..."
        $DOCKER_COMPOSE down
        ;;
    restart)
        echo "Restarting sleeper-backend..."
        $DOCKER_COMPOSE restart
        ;;
    logs)
        $DOCKER_COMPOSE logs -f sleeper-backend
        ;;
    status)
        $DOCKER_COMPOSE ps
        ;;
    clean)
        echo "Cleaning up..."
        $DOCKER_COMPOSE down -v
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
