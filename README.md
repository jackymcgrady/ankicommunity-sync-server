# Anki Sync Server

Self-hosted Anki sync server with AWS Cognito authentication, PostgreSQL user management, and automatic HTTPS certificates.

## Features

- 🔐 **AWS Cognito Authentication** - Secure user management with Cognito User Pool
- 🗄️ **PostgreSQL Integration** - User profiles and metadata stored in PostgreSQL
- 📁 **UUID-based Collections** - Collections stored using stable Cognito UUIDs
- 🔒 **Automatic HTTPS** - Let's Encrypt certificates with nginx reverse proxy
- 📦 **Docker Containerized** - Easy deployment and management
- 🛡️ **NFS Lock Prevention** - Automatic cleanup of stale collection locks

## Quick Start

```bash
# Configure environment
cp .env.example .env && nano .env     # fill in AWS + Cognito + domain + PostgreSQL

# Launch server
docker-compose -f docker-compose.latest.yml up -d

# Verify
curl -k https://<your-domain>/sync/hostKey   # should return JSON
```

Connect Anki clients to `https://<your-domain>` using your Cognito credentials.

## Configuration

Required environment variables in `.env`:

| Variable | Purpose |
|----------|---------|
| AWS_ACCESS_KEY_ID | AWS credentials for Cognito |
| AWS_SECRET_ACCESS_KEY | AWS credentials for Cognito |
| ANKISYNCD_COGNITO_USER_POOL_ID | Cognito User Pool ID |
| ANKISYNCD_COGNITO_CLIENT_ID | Cognito App Client ID |
| ANKISYNCD_COGNITO_CLIENT_SECRET | Cognito App Client Secret |
| ANKISYNCD_COGNITO_REGION | AWS region (default: ap-southeast-1) |
| POSTGRES_PASSWORD | PostgreSQL database password |
| POSTGRES_HOST | PostgreSQL host (default: localhost) |
| POSTGRES_USER | PostgreSQL username (default: anki) |
| POSTGRES_DB | PostgreSQL database name (default: anki) |
| DOMAIN_NAME | Your domain name |
| EMAIL | Email for Let's Encrypt certificates |
| DATA_VOLUME_SOURCE | Host path for user data (default: ./efs) |
| CONTAINER_USER_ID | Container user ID (default: 1001) |
| CONTAINER_GROUP_ID | Container group ID (default: 65533) |

## User Management

### How Authentication Works

1. Users authenticate with Cognito credentials (email/username + password)
2. Server extracts permanent UUID from Cognito `sub` claim
3. User profile created/updated in PostgreSQL with UUID link
4. Collections stored in `./efs/collections/{cognito-uuid}/`

### Migration from Username-based System

If migrating from an older version using usernames for folder names:

```bash
# Run migration script (dry run first)
python3 scripts/migrate_user_uuids.py --data-root ./efs

# Execute migration after reviewing
python3 scripts/migrate_user_uuids.py --execute --data-root ./efs
```

See [README_MIGRATION.md](README_MIGRATION.md) for detailed migration instructions.

## Operations

```bash
# Start/stop
docker-compose -f docker-compose.latest.yml up -d
docker-compose -f docker-compose.latest.yml down

# View logs
docker-compose -f docker-compose.latest.yml logs -f anki-sync-server

# Reset user collection (use UUID, not username)
echo "yes" | python3 scripts/reset_user_collection.py <cognito-uuid> --confirm --data-root ./efs
```

**Important**: 
- User data is stored in `./efs/collections/` directory
- Collections are organized by Cognito UUID, not username
- PostgreSQL database contains user profiles and metadata
- When deploying with a webapp, ensure both containers use matching user IDs (1001:65533) for shared data access

## Troubleshooting

**User can't sync / "no collection found"?**
```bash
# Check user's UUID in database
PGPASSWORD=<password> psql -h localhost -U <username> -d <database> -c "SELECT uuid, name FROM profiles WHERE name = 'username';"

# Clear sessions and restart
rm -f ./efs/session.db*
docker-compose -f docker-compose.latest.yml restart anki-sync-server
```

**Collection locked ("Anki already open")?**
```bash
# Remove NFS/WAL lock files
sudo ./scripts/cleanup-nfs-locks.sh
# Or manually:
sudo rm -f ./efs/collections/*/.*nfs* ./efs/collections/*/*.anki2-wal ./efs/collections/*/*-shm
docker-compose -f docker-compose.latest.yml restart anki-sync-server
```

**Check authentication:**
```bash
docker-compose -f docker-compose.latest.yml logs anki-sync-server | grep -i "auth\|cognito"
```

**Reset user collection:**
```bash
# Use the user's Cognito UUID (not username)
echo "yes" | python3 scripts/reset_user_collection.py <cognito-uuid> --confirm --data-root ./efs
```

**Database issues:**
```bash
# Check PostgreSQL connection
PGPASSWORD=<password> psql -h localhost -U <username> -d <database> -c "\dt"

# View user profiles
PGPASSWORD=<password> psql -h localhost -U <username> -d <database> -c "SELECT profile_id, name, uuid, created_at FROM profiles;"
```

**Check collection folders:**
```bash
ls -la ./efs/collections/  # Should show UUID-named folders
```

**"Readonly database" or permission errors:**
```bash
# Fix permissions for shared data access with webapp
sudo chown -R 1001:65533 ./efs/
sudo chmod -R 755 ./efs/

# Remove corrupted session files
rm -f ./efs/session.db*

# Restart containers
docker-compose -f docker-compose.latest.yml restart
```

**Sync stuck on "checking" status:**
This is normal during metadata exchange. The sync is likely working correctly. Check logs for ✅ SUCCESS messages:
```bash
docker-compose -f docker-compose.latest.yml logs anki-sync-server | grep -E "(SUCCESS|ERROR|collection)"
```

## Database Schema

The `profiles` table contains:
- `profile_id` - Auto-incrementing primary key
- `uuid` - Cognito user's permanent UUID (`sub` claim)
- `name` - Cognito username  
- `created_at` - Profile creation timestamp
- `is_active` - User active status

Foreign key relationships exist with `deck_stats`, `decks`, `note_types`, and `pass` tables.
