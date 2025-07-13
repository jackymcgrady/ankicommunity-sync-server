#!/bin/bash
# Rebuild and restart script

echo "=== Rebuilding and restarting Anki Sync Server ==="

# Stop containers
echo "Stopping containers..."
docker compose -f docker-compose.prod.yml down

# Rebuild images
echo "Rebuilding images..."
docker compose -f docker-compose.prod.yml build --no-cache

# Start containers
echo "Starting containers..."
docker compose -f docker-compose.prod.yml up -d

# Show status
echo "Container status:"
docker compose -f docker-compose.prod.yml ps

echo "=== Restart completed ==="
