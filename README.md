# Anki Sync Server

Self-hosted Anki sync server with AWS Cognito authentication, SQLite user management, and automatic HTTPS certificates.

## Features

- 🔐 **AWS Cognito Authentication** - Secure user management with Cognito User Pool
- 💾 **SQLite User Management** - User profiles and metadata stored in SQLite database
- 📁 **UUID-based Collections** - Collections stored using stable Cognito UUIDs
- 🔒 **Automatic HTTPS** - Let's Encrypt certificates with nginx reverse proxy
- 📦 **Docker Containerized** - Easy deployment and management
- 🛡️ **NFS Lock Prevention** - Automatic cleanup of stale collection locks

## Quick Start

```bash
# Configure environment
cp .env.example .env && nano .env     # fill in AWS + Cognito + domain configuration

# Launch server
docker-compose -f docker-compose.latest.yml up -d

# Verify
curl -k https://<your-domain>/sync/hostKey   # should return JSON
```

Connect Anki clients to `https://<your-domain>` using your Cognito credentials.

## Configuration

Required environment variables in `.env`:

| Variable | Purpose | Default |
|----------|---------|---------|
| AWS_ACCESS_KEY_ID | AWS credentials for Cognito | - |
| AWS_SECRET_ACCESS_KEY | AWS credentials for Cognito | - |
| AWS_DEFAULT_REGION | AWS region | ap-southeast-1 |
| ANKISYNCD_COGNITO_USER_POOL_ID | Cognito User Pool ID | - |
| ANKISYNCD_COGNITO_CLIENT_ID | Cognito App Client ID | - |
| ANKISYNCD_COGNITO_CLIENT_SECRET | Cognito App Client Secret | - |
| ANKISYNCD_COGNITO_REGION | AWS region for Cognito | ap-southeast-1 |
| DOMAIN_NAME | Your domain name | - |
| EMAIL | Email for Let's Encrypt certificates | - |
| SSL_MODE | SSL certificate mode | letsencrypt |
| DEV_MODE | Enable development mode | false |
| DATA_VOLUME_SOURCE | Host path for user data | ./efs |
| CONTAINER_USER_ID | Container user ID | 1001 |
| CONTAINER_GROUP_ID | Container group ID | 65533 |
| MEMORY_LIMIT | Container memory limit | 512M |
| CPU_LIMIT | Container CPU limit | 1.0 |

## User Management

### How Authentication Works

1. Users authenticate with Cognito credentials (email/username + password)
2. Server extracts permanent UUID from Cognito `sub` claim
3. User profile created/updated in SQLite database with UUID link
4. Collections stored in `./efs/collections/{cognito-uuid}/`

### User Management

User profiles are stored in a SQLite database (`session.db`) with the following structure:
- `profiles` table with UUID, username, and sync metadata
- Automatic profile creation on first sync
- UUID-based collection organization for stability

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
- SQLite database (`session.db`) contains user profiles and sync metadata
- When deploying with a webapp, ensure both containers use matching user IDs (1001:65533) for shared data access
- Collections use server mode (`server=True`) for proper USN tracking

## Troubleshooting

**User can't sync / "no collection found"?**
```bash
# Check user's UUID in SQLite database
sqlite3 ./efs/session.db "SELECT uuid, name FROM profiles WHERE name = 'username';"

# Clear sessions and restart
rm -f ./efs/session.db*
docker-compose -f docker-compose.latest.yml restart anki-sync-server-nginx
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
# Check SQLite database structure
sqlite3 ./efs/session.db ".tables"

# View user profiles
sqlite3 ./efs/session.db "SELECT profile_id, name, uuid, created_at FROM profiles;"
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
docker-compose -f docker-compose.latest.yml logs anki-sync-server-nginx | grep -E "(SUCCESS|ERROR|collection)"
```

**Recent USN Sync Fix:**
The server now uses consistent server-mode (`server=True`) collection access to prevent USN mismatches that caused forced one-way syncs. This ensures all collection operations use the same USN tracking behavior for reliable synchronization.

## Database Schema

The SQLite database (`session.db`) contains user profiles and sync metadata:

- `profiles` table:
  - `profile_id` - Auto-incrementing primary key
  - `uuid` - Cognito user's permanent UUID (`sub` claim)
  - `name` - Cognito username  
  - `created_at` - Profile creation timestamp
  - `is_active` - User active status

- Additional tables for sync state management and session tracking
