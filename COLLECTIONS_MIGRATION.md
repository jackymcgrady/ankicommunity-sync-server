# Collection Data Migration Guide

## Overview
Collection data is stored in the `./collections/` folder and is persistent across container restarts and deployments.

## Migrating Collections to a New Server

1. **Stop the container** on the source server:
   ```bash
   docker-compose down
   ```

2. **Copy the collections folder** to your new server:
   ```bash
   # From source server
   tar -czf collections-backup.tar.gz collections/
   scp collections-backup.tar.gz user@new-server:/path/to/ankicommunity-sync-server/
   
   # On new server
   cd /path/to/ankicommunity-sync-server/
   tar -xzf collections-backup.tar.gz
   ```

3. **Start the container** on the new server:
   ```bash
   docker-compose up -d
   ```

## Data Structure
- Collections are stored in `./collections/users/`
- Each user has their own subdirectory
- Structure: `./collections/users/{username}/collection.anki2` and `./collections/users/{username}/collection.media/`

## Volume Mounting
The docker-compose.yml maps `./collections:/app/collections` for persistence.