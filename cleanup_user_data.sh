#!/bin/bash
# Cleanup script for user data

USER_EMAIL="huyupingxdf@yahoo.com"
DATA_DIR="/opt/anki-sync-server/data"

echo "Cleaning up data for user: $USER_EMAIL"

# Stop container first
docker compose -f docker-compose.prod.yml down

# Remove user's collection files
if [ -d "$DATA_DIR/collections/$USER_EMAIL" ]; then
    echo "Removing collection directory: $DATA_DIR/collections/$USER_EMAIL"
    rm -rf "$DATA_DIR/collections/$USER_EMAIL"
fi

# Remove any session files (if they exist)
if [ -f "$DATA_DIR/sessions.db" ]; then
    echo "Clearing sessions database"
    sqlite3 "$DATA_DIR/sessions.db" "DELETE FROM sessions WHERE username = '$USER_EMAIL';" 2>/dev/null || true
fi

# Remove any user-specific logs or temp files
find "$DATA_DIR" -name "*$USER_EMAIL*" -type f -delete 2>/dev/null || true

echo "Cleanup completed for $USER_EMAIL"
echo "User authentication record preserved"
