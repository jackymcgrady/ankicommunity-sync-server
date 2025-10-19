#!/bin/bash
# SSL Certificate Renewal Script for AnkiPi
# This script renews Let's Encrypt certificates and reloads nginx

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"

echo "[$(date)] Starting certificate renewal..."

# Run certbot renewal
docker run --rm \
  -v "${PROJECT_DIR}/letsencrypt:/etc/letsencrypt" \
  -v "${PROJECT_DIR}/certbot-www:/var/www/certbot" \
  -v "${PROJECT_DIR}/logs/certbot:/var/log/letsencrypt" \
  certbot/certbot renew --no-random-sleep-on-renew

# Check if renewal was successful
if [ $? -eq 0 ]; then
    echo "[$(date)] Certificate renewal completed successfully"
    
    # Reload nginx to apply new certificates
    docker exec anki-nginx-proxy nginx -s reload
    
    if [ $? -eq 0 ]; then
        echo "[$(date)] Nginx reloaded successfully"
    else
        echo "[$(date)] ERROR: Failed to reload nginx"
        exit 1
    fi
else
    echo "[$(date)] ERROR: Certificate renewal failed"
    exit 1
fi

echo "[$(date)] Certificate renewal process completed"
