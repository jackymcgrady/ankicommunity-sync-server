#!/bin/bash

# Docker Deployment Script for Anki Sync Server
# Usage: ./scripts/docker-deploy.sh [environment]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Configuration
REGISTRY="ghcr.io"
IMAGE_NAME="jackymcgrady/ankicommunity-sync-server"
DEFAULT_TAG="latest"
COMPOSE_FILE="docker-compose.prod.yml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

print_header() {
    echo -e "${BLUE}[DEPLOY]${NC} $1"
}

# Parse command line arguments
ENVIRONMENT="${1:-staging}"
TAG="${2:-$DEFAULT_TAG}"
FORCE_PULL="${3:-false}"

print_header "Deploying Anki Sync Server - Environment: $ENVIRONMENT, Tag: $TAG"

# Change to project directory
cd "$PROJECT_DIR"

# Function to check if running as root or with sudo
check_permissions() {
    if [[ $EUID -ne 0 ]] && ! groups | grep -q docker; then
        print_error "This script requires root privileges or docker group membership"
        exit 1
    fi
}

# Function to backup current data
backup_data() {
    if [[ -d "./data" ]]; then
        BACKUP_DIR="./backups/$(date +%Y%m%d_%H%M%S)"
        print_status "Creating backup at $BACKUP_DIR..."
        mkdir -p "$BACKUP_DIR"
        cp -r ./data "$BACKUP_DIR/"
        print_status "Backup created successfully"
    fi
}

# Function to pull latest images
pull_images() {
    print_status "Pulling latest Docker images..."
    docker pull "$REGISTRY/$IMAGE_NAME:$TAG" || {
        print_error "Failed to pull main image"
        exit 1
    }
    
    # Pull proxy image if exists
    if docker manifest inspect "$REGISTRY/$IMAGE_NAME-proxy:$TAG" > /dev/null 2>&1; then
        docker pull "$REGISTRY/$IMAGE_NAME-proxy:$TAG" || {
            print_warning "Failed to pull proxy image, continuing..."
        }
    fi
}

# Function to stop existing containers
stop_containers() {
    print_status "Stopping existing containers..."
    if docker-compose -f "$COMPOSE_FILE" ps -q | grep -q .; then
        docker-compose -f "$COMPOSE_FILE" down --remove-orphans
    fi
}

# Function to start new containers
start_containers() {
    print_status "Starting new containers..."
    
    # Export environment variables
    export ANKI_IMAGE="$REGISTRY/$IMAGE_NAME:$TAG"
    export ANKI_PROXY_IMAGE="$REGISTRY/$IMAGE_NAME-proxy:$TAG"
    
    # Start containers
    docker-compose -f "$COMPOSE_FILE" up -d
    
    # Wait for containers to be ready
    print_status "Waiting for containers to be ready..."
    timeout=30
    while [[ $timeout -gt 0 ]]; do
        if docker-compose -f "$COMPOSE_FILE" ps | grep -q "healthy\|Up"; then
            break
        fi
        sleep 2
        ((timeout--))
    done
    
    if [[ $timeout -eq 0 ]]; then
        print_error "Containers failed to start properly"
        docker-compose -f "$COMPOSE_FILE" logs
        exit 1
    fi
}

# Function to verify deployment
verify_deployment() {
    print_status "Verifying deployment..."
    
    # Check if containers are running
    if ! docker-compose -f "$COMPOSE_FILE" ps | grep -q "Up"; then
        print_error "Containers are not running"
        return 1
    fi
    
    # Check if service is responding
    if command -v curl > /dev/null; then
        if curl -f -s http://localhost:27701/status > /dev/null 2>&1; then
            print_status "Service is responding correctly"
        else
            print_warning "Service health check failed"
        fi
    fi
    
    print_status "Deployment verification completed"
}

# Function to cleanup old images
cleanup_old_images() {
    print_status "Cleaning up old Docker images..."
    docker image prune -f
    
    # Remove old versions of our images (keep last 3)
    docker images "$REGISTRY/$IMAGE_NAME" --format "table {{.Repository}}:{{.Tag}}" | \
        tail -n +4 | \
        xargs -r docker rmi 2>/dev/null || true
}

# Main deployment process
main() {
    print_header "Starting deployment process..."
    
    # Check permissions
    check_permissions
    
    # Create backup
    backup_data
    
    # Pull images if needed
    if [[ "$FORCE_PULL" == "true" ]] || ! docker images | grep -q "$REGISTRY/$IMAGE_NAME:$TAG"; then
        pull_images
    fi
    
    # Stop existing containers
    stop_containers
    
    # Start new containers
    start_containers
    
    # Verify deployment
    verify_deployment
    
    # Cleanup
    cleanup_old_images
    
    print_header "Deployment completed successfully!"
    print_status "Anki Sync Server is now running with image: $REGISTRY/$IMAGE_NAME:$TAG"
    
    # Show status
    docker-compose -f "$COMPOSE_FILE" ps
}

# Command handling
case "${ENVIRONMENT}" in
    "staging"|"production")
        main
        ;;
    "rollback")
        TAG="${2:-previous}"
        print_header "Rolling back to tag: $TAG"
        FORCE_PULL="true"
        main
        ;;
    "status")
        print_status "Current deployment status:"
        docker-compose -f "$COMPOSE_FILE" ps
        ;;
    "logs")
        print_status "Showing deployment logs:"
        docker-compose -f "$COMPOSE_FILE" logs -f
        ;;
    "help"|*)
        echo "Docker Deployment Script for Anki Sync Server"
        echo ""
        echo "Usage: $0 [environment] [tag] [force_pull]"
        echo ""
        echo "Environments:"
        echo "  staging     Deploy to staging environment"
        echo "  production  Deploy to production environment"
        echo "  rollback    Rollback to previous version"
        echo "  status      Show current deployment status"
        echo "  logs        Show deployment logs"
        echo "  help        Show this help message"
        echo ""
        echo "Examples:"
        echo "  $0 staging                    # Deploy latest to staging"
        echo "  $0 production v2.4.0         # Deploy specific version to production"
        echo "  $0 rollback                   # Rollback to previous version"
        echo "  $0 production latest true     # Force pull and deploy latest"
        ;;
esac 