#!/bin/bash

# Docker Development Script for Anki Sync Server
# Usage: ./scripts/docker-dev.sh [command]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Change to project directory
cd "$PROJECT_DIR"

# Command handling
case "${1:-help}" in
    "build")
        print_status "Building Docker images..."
        docker-compose build
        ;;
    
    "up")
        print_status "Starting development environment..."
        docker-compose up -d
        print_status "Anki Sync Server is running at http://localhost:27701"
        ;;
    
    "down")
        print_status "Stopping development environment..."
        docker-compose down
        ;;
    
    "restart")
        print_status "Restarting development environment..."
        docker-compose down
        docker-compose up -d
        ;;
    
    "logs")
        print_status "Showing logs..."
        docker-compose logs -f anki-sync-server
        ;;
    
    "shell")
        print_status "Opening shell in container..."
        docker-compose exec anki-sync-server bash
        ;;
    
    "test")
        print_status "Running tests in container..."
        docker-compose exec anki-sync-server python -m pytest tests/
        ;;
    
    "clean")
        print_status "Cleaning up Docker resources..."
        docker-compose down --volumes --remove-orphans
        docker system prune -f
        ;;
    
    "prod")
        print_status "Starting production environment..."
        docker-compose --profile production up -d
        print_status "Production HTTP server is running at http://localhost:27704"
        print_status "Production HTTPS server is running at https://localhost:27705"
        ;;
    
    "https")
        print_status "Starting with HTTPS proxy..."
        docker-compose --profile https up -d
        print_status "HTTP server is running at http://localhost:27701"
        print_status "HTTPS server is running at https://localhost:27703"
        ;;
    
    "certs")
        print_status "Generating SSL certificates for HTTPS..."
        mkdir -p certs
        if [ ! -f certs/server.crt ] || [ ! -f certs/server.key ]; then
            openssl req -x509 -newkey rsa:4096 -keyout certs/server.key -out certs/server.crt -days 365 -nodes -subj "/C=US/ST=State/L=City/O=AnkiSyncServer/CN=localhost"
            chmod 600 certs/server.key
            chmod 644 certs/server.crt
            print_status "SSL certificates generated successfully"
            print_status "Certificate: ./certs/server.crt"
            print_status "Private key: ./certs/server.key"
        else
            print_status "SSL certificates already exist"
        fi
        ;;
    
    "status")
        print_status "Container status:"
        docker-compose ps
        ;;
    
    "help"|*)
        echo "Docker Development Script for Anki Sync Server"
        echo ""
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  build     Build Docker images"
        echo "  up        Start development environment"
        echo "  down      Stop development environment"
        echo "  restart   Restart development environment"
        echo "  logs      Show container logs"
        echo "  shell     Open shell in container"
        echo "  test      Run tests in container"
        echo "  clean     Clean up Docker resources"
        echo "  prod      Start production environment"
        echo "  https     Start with HTTPS proxy"
        echo "  certs     Generate SSL certificates for HTTPS"
        echo "  status    Show container status"
        echo "  help      Show this help message"
        echo ""
        echo "Examples:"
        echo "  $0 build && $0 up    # Build and start development"
        echo "  $0 certs && $0 https # Generate certs and start HTTPS"
        echo "  $0 logs              # Follow logs"
        echo "  $0 clean             # Clean up everything"
        ;;
esac 