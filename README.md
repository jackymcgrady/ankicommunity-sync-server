# Anki Sync Server

A modern, open-source implementation of Anki's v2.1.57+ sync protocol.  
If you manage multiple Anki clients (desktop, mobile, web) and need a **self-hosted** alternative to AnkiWeb, this server keeps every device in lock-step—collections, media, and change history included.

## 🚀 Quick Start

### Local Development
```bash
# Clone and start with Docker
git clone https://github.com/jackymcgrady/ankicommunity-sync-server.git
cd ankicommunity-sync-server
./scripts/docker-dev.sh https

# Create a user
python3 add_email_user.py

# Connect Anki to: https://localhost:27703
```

### Production Deployment (AWS Lightsail)
```bash
# 1. Set up your domain DNS to point to your server
# 2. Configure environment
cp env.production.example .env
# Edit .env with your domain and email

# 3. Deploy with automatic SSL
./scripts/aws-deploy.sh

# 4. Create users and start syncing
python3 add_email_user.py
```

---

## The User Story
1. **Edit Anywhere** – Study on your phone during the commute, then refine cards on your laptop at night.
2. **Hit *Sync*** – Each client contacts the same endpoint (`/sync`) over HTTP and authenticates with your credentials.
3. **See Magic** – The server reconciles review logs, note edits, card scheduling, and media additions so every device looks identical the next time you open Anki.

Behind that *Sync* button lives a carefully orchestrated sequence of database merges, conflict resolution, and media transfers—performed safely, atomically, and as fast as possible.

---

## Architecture at a Glance
• **Protocol Compatibility** – Implements the exact RPC contract used by official Anki 2.1.57+, including media-sync sub-protocol (`/msync`).  
• **SQLite-First Storage** – Each profile stores its `collection.anki2` plus companion media databases on the server.  
• **Write-Ahead Logging (WAL)** – Concurrency-friendly mode lets the server serve parallel read/write transactions without blocking.  
• **Batch Streaming** – Large payloads—card revlogs, media blobs—stream in configurable chunks to minimize memory pressure.  
• **Pythonic Core** – Pure-Python implementation (3.9+) with minimal external deps; easy to read, extend, and debug.

---

## Core Components
| Module | Responsibility |
| ------ | -------------- |
| `sync_app.py` & `server.py` | ASGI/WSGI entry points; route RPC calls to handlers |
| `sync.py` | High-level orchestration of the sync transaction |
| `collection/` | Thin wrapper over SQLite collection with versioned schema upgrades |
| `full_sync/` | Fallback path when incremental sync cannot resolve divergence |
| `media_manager.py` | Deduplicates, normalizes, and streams media files |
| `sessions/` | Short-lived auth tokens reused by mobile clients |
| `users/` | Pluggable user backend (simple JSON, SQLite, or custom) |

Each component is **loosely coupled** so you can swap backends or add metrics without touching core logic.

---

## Sync Workflow (Incremental)
1. **Handshake** – Client sends local `mod` and `usn`; server decides if fast-forward, merge, or full-sync is needed.
2. **Graves & Revs** – Deleted objects and review logs arrive first, applied in isolated transactions.
3. **Chunked Changes** – New/updated notes, cards, decks, etc., stream in batched JSON.
4. **Media Inventory** – Separate `/msync` endpoint exchanges file hashes and pushes/pulls missing media.
5. **Finish & Ack** – Server returns new `usn` and updated deck config so the client can update scheduling.

All steps run inside a **single WAL-protected transaction**; on any error the database rolls back to a pre-sync snapshot.

---

## Data Integrity & Safety
* **Checksum validation** on every received collection file and media chunk.
* **Automatic schema migrations** keep legacy clients functional.
* **Conflict resolution** follows upstream Anki logic (newer `mod` wins, deterministic tie-breakers).
* **Locked writes** ensure two devices never overwrite each other's work mid-sync.

---

## Configuration
Settings can be supplied via **environment variables** (recommended) or a classic `ankisyncd.conf` file.

| Env Var | Purpose | Default |
| ------- | ------- | ------- |
| `ANKISYNCD_HOST` | Bind address | `127.0.0.1` |
| `ANKISYNCD_PORT` | TCP port | `27701` |
| `ANKISYNCD_COLLECTIONS_PATH` | Where user data lives | `./collections` |
| `ANKISYNCD_AUTH_DB_PATH` | Auth backend (when using SQLite) | `./auth.db` |
| `ANKISYNCD_LOG_LEVEL` | `DEBUG` / `INFO` | `INFO` |

---

## Running Locally (Developer Mode)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r src/requirements.txt
pip install -e src
python -m ankisyncd
```
The server now listens on `http://127.0.0.1:27701`—point your client there under *Preferences → Sync*.

---

## 🔐 Authentication Database Management

### Understanding Auth Database Location

The auth database location depends on your deployment configuration:

#### Development (Local)
- **Config file**: `src/ankisyncd.conf` sets `auth_db_path = ./auth.db`
- **Working directory**: Server runs from project root
- **Actual location**: `./auth.db` (project root)
- **Docker mount**: `./auth.db:/app/auth.db` (if using docker-compose.override.yml)

#### Production
- **Environment variable**: `ANKISYNCD_AUTH_DB_PATH=/app/collections/auth.db`
- **Docker volume**: `./data/collections:/app/collections`
- **Actual location**: `./data/collections/auth.db` (host) → `/app/collections/auth.db` (container)

### Creating Users

#### Method 1: Using Python Script (Recommended)
```python
#!/usr/bin/env python3
import sqlite3
import hashlib
import binascii
import os

def create_auth_db(db_path, username, password):
    """Create auth database with user credentials"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create auth table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS auth (
            username VARCHAR PRIMARY KEY, 
            hash VARCHAR
        )
    """)
    
    # Create password hash (matches server's method)
    salt = binascii.b2a_hex(os.urandom(8))
    pass_hash = (
        hashlib.sha256((username + password).encode() + salt).hexdigest()
        + salt.decode()
    )
    
    # Add user
    cursor.execute("INSERT OR REPLACE INTO auth VALUES (?, ?)", (username, pass_hash))
    conn.commit()
    conn.close()
    print(f"Created auth.db with user: {username}")

# Usage examples:
# Development: create_auth_db("./auth.db", "user@example.com", "password123")
# Production: create_auth_db("./data/collections/auth.db", "user@example.com", "password123")
```

#### Method 2: Using Docker Exec (For Running Containers)
```bash
# Development container
docker exec anki-sync-server-dev python3 -c "
from ankisyncd.users.sqlite_manager import SqliteUserManager
mgr = SqliteUserManager('/app/auth.db', '/app/collections')
mgr.add_user('user@example.com', 'password123')
print('User added successfully')
"

# Production container
docker exec anki-sync-server-prod python3 -c "
from ankisyncd.users.sqlite_manager import SqliteUserManager
mgr = SqliteUserManager('/app/collections/auth.db', '/app/collections')
mgr.add_user('user@example.com', 'password123')
print('User added successfully')
"
```

### Verifying Authentication

```bash
# Test authentication (adjust paths for your deployment)
docker exec anki-sync-server-prod python3 -c "
from ankisyncd.users.sqlite_manager import SqliteUserManager
mgr = SqliteUserManager('/app/collections/auth.db', '/app/collections')
result = mgr.authenticate('user@example.com', 'password123')
print('Authentication test:', 'SUCCESS' if result else 'FAILED')
users = mgr.user_list()
print('Users in database:', users)
"
```

### Troubleshooting Auth Issues

#### Common Problems:
1. **"no such table: auth"** → Database doesn't exist or is empty
2. **"Authentication failed for nonexistent user"** → User not in database
3. **"Auth DB doesn't exist"** → Wrong path or file not created

#### Debug Steps:
```bash
# Check if auth.db exists and location
ls -la ./auth.db                    # Development
ls -la ./data/collections/auth.db   # Production

# Check database contents
sqlite3 ./data/collections/auth.db "SELECT username FROM auth;"

# Check container logs for auth path
docker logs anki-sync-server-prod 2>&1 | grep "auth_db_path"
```

#### Key Learning: Environment Variables Override Config Files
- The production `docker-compose.prod.yml` sets `ANKISYNCD_AUTH_DB_PATH=/app/collections/auth.db`
- This overrides the `auth_db_path = ./auth.db` setting in `ankisyncd.conf`
- Always check both config files AND environment variables to determine the actual auth database location

---

## ⚠️ Common Deployment Issues & Solutions

### 1. AttributeError: 'SyncUserSession' object has no attribute 'username'
**Symptom:** Sync fails with this error even though connection is successful.
**Cause:** Code tries to access `session.username` but should use `session.name`.
**Solution:** Replace all instances of `session.username` with `session.name` in sync_app.py.

### 2. HTTPS Proxy Can't Connect to Sync Server
**Symptom:** Proxy logs show "Name or service not known" errors.
**Cause:** Service name mismatch between Docker containers.
**Solution:** 
- Ensure SYNC_SERVER_URL environment variable points to correct container name
- For Cognito setup: `http://anki-sync-server-cognito:27702`
- Rebuild containers after changing environment variables

### 3. HTTPS Proxy Not Starting
**Symptom:** Only sync server starts, no proxy container.
**Cause:** Docker Compose profiles not activated.
**Solution:** Use `--profile https` flag:
```bash
docker-compose -f docker-compose.yml -f docker-compose.cognito.yml --profile https up -d
```

### 4. CognitoUserManager Initialization Error
**Symptom:** `TypeError: CognitoUserManager.__init__() takes 2 positional arguments but 3 were given`
**Cause:** Mismatch between expected constructor signature and usage.
**Solution:** Pass only config dict to CognitoUserManager:
```python
# Wrong:
return CognitoUserManager(config.get("data_root"), cognito_config)
# Correct:
return CognitoUserManager(config)
```

### 5. Protobuf Compatibility Issues
**Symptom:** `ImportError: cannot import name 'runtime_version' from 'google.protobuf'`
**Cause:** Version mismatch between Anki and protobuf packages.
**Solution:** Pin compatible versions in requirements.txt:
```
anki==24.4.1
protobuf>=4.21,<5
```

### 6. Server Accessible but Can't Login via Domain
**Symptom:** Direct access works (`http://localhost:27702`) but domain fails.
**Cause:** Multiple issues - container networking, proxy configuration, DNS.
**Debug Steps:**
1. Check both containers are running: `docker ps`
2. Verify proxy logs: `docker logs anki-https-proxy-cognito`
3. Test direct access: `curl http://localhost:27702/sync/hostKey`
4. Check DNS resolution of your domain

### Quick Recovery Commands
```bash
# Stop everything and rebuild with fixes
docker-compose down
docker-compose -f docker-compose.yml -f docker-compose.cognito.yml --profile https up --build -d

# Check status
docker ps
docker logs anki-sync-server-cognito --tail 10
docker logs anki-https-proxy-cognito --tail 10
```

---

## 🐳 Docker Deployment

A complete Docker setup is provided for development, testing, and production deployment with full HTTPS support.

### Quick Start

```bash
# Development with HTTP only
./scripts/docker-dev.sh up

# Development with HTTPS (recommended)
./scripts/docker-dev.sh certs   # Generate SSL certificates
./scripts/docker-dev.sh https   # Start with HTTPS proxy

# Production testing
./scripts/docker-dev.sh prod
```

**Access URLs:**
- HTTP: `http://localhost:27701`
- HTTPS: `https://localhost:27703`

### Essential Commands

```bash
# Container Management
./scripts/docker-dev.sh build    # Build Docker images
./scripts/docker-dev.sh up       # Start development environment
./scripts/docker-dev.sh https    # Start with HTTPS proxy
./scripts/docker-dev.sh down     # Stop all containers
./scripts/docker-dev.sh restart  # Restart containers
./scripts/docker-dev.sh status   # Check container status

# Monitoring & Debugging
./scripts/docker-dev.sh logs     # View server logs
docker-compose logs -f           # Real-time logs from all containers
docker-compose logs -t --tail=50 # Recent logs with timestamps
docker exec -it anki-sync-server-dev bash  # Shell access

# SSL Certificate Management
./scripts/setup-https-certs.sh self-signed   # Generate self-signed cert
./scripts/setup-https-certs.sh letsencrypt   # Get Let's Encrypt cert
./scripts/setup-https-certs.sh info          # Check certificate info
```

### Production Deployment

```bash
# Deploy to production server
./scripts/docker-deploy.sh production latest

# Check deployment status
./scripts/docker-deploy.sh status

# View production logs
./scripts/docker-deploy.sh logs

# Rollback if needed
./scripts/docker-deploy.sh rollback
```

### Docker Architecture

- **Multi-stage Dockerfile**: Optimized builds for development and production
- **HTTPS Proxy**: Automatic SSL/TLS termination with certificate generation
- **Health Checks**: Built-in container health monitoring
- **Volume Persistence**: Data survives container restarts
- **GitHub Actions**: Automated image building and publishing

### Monitoring Sync Activity

```bash
# Real-time sync monitoring
docker-compose logs -f | grep -E "(sync|meta|hostKey|msync)"

# Check container resources
docker stats

# Inspect specific sync requests
docker logs anki-sync-server-dev --tail=100
```

### Troubleshooting

```bash
# Clean restart
docker-compose down --volumes --remove-orphans
docker system prune -f
./scripts/docker-dev.sh build && ./scripts/docker-dev.sh https

# Check port conflicts
lsof -i :27701 && lsof -i :27703

# Container debugging
docker inspect anki-sync-server-dev
docker exec anki-sync-server-dev ps aux
```

For complete Docker documentation, see [`DOCKER_GUIDE.md`](DOCKER_GUIDE.md).

---

## 🚨 Critical Deployment Tips

### Modern Anki Client Compatibility (v25.02+)

**Problem**: Modern Anki clients (v25.02+) failed with "Exception: expected auth" and "missing original_size" errors.

**Root Causes & Solutions**:

#### 1. Authentication Flow Issues
- **Issue**: Client discovery requests weren't triggering authentication dialogs
- **Fix**: Return HTTP 400 "expected auth" for discovery requests (`{"k": ""}` with empty body)
- **Code**: Modified `sync_app.py` authentication handling to properly signal auth requirement

#### 2. Missing anki-original-size Header
- **Issue**: All zstd-compressed responses must include `anki-original-size` header with uncompressed byte count
- **Fix**: Updated `chunked` decorator to handle `(body, original_size)` tuples and set headers
- **Impact**: Critical for media sync operations and all compressed responses

#### 3. Request Body Parsing for Streaming Clients
- **Issue**: Modern clients stream request bodies without `Content-Length` headers using chunked transfer encoding
- **Fix**: Enhanced `get_body_data()` to handle:
  - Missing/empty `Content-Length` headers
  - Manual chunked transfer decoding when WSGI lacks support
  - Non-blocking reads to prevent 30-second timeouts
- **Code**: Added chunked parsing logic in `sync_app.py`

#### 4. Media Sync Response Format
- **Issue**: Media operations returned inconsistent response formats
- **Fix**: All media sync responses now return `(payload, original_size)` tuples:
  - JSON responses: zstd-compressed with size header
  - Binary downloads: raw data with size header
- **Impact**: Eliminates "missing original size" errors during media sync

#### 5. Database Initialization
- **Issue**: Server crashed with "no such table: auth" on fresh deployments
- **Fix**: Auto-create auth database and tables on startup if missing
- **Code**: Enhanced `sqlite_manager.py` initialization

### Essential Configuration

```bash
# User Management - Create persistent auth database (Production)
docker exec anki-sync-server-prod python -c "
from ankisyncd.users.sqlite_manager import SqliteUserManager
mgr = SqliteUserManager('/app/collections/auth.db', '/app/collections')
mgr.add_user('your-email@example.com', 'your-password')
print('User added successfully')
"

# Verify user authentication (Production)
docker exec anki-sync-server-prod python -c "
from ankisyncd.users.sqlite_manager import SqliteUserManager
mgr = SqliteUserManager('/app/collections/auth.db', '/app/collections')
result = mgr.authenticate('your-email@example.com', 'your-password')
print('Auth test:', result)
"
```

### Persistent Data Setup

```bash
# Create persistent data directory
mkdir -p /opt/anki-sync-server/data

# Docker compose override for persistence
cat > docker-compose.override.yml << 'EOF'
version: '3.8'
services:
  anki-sync-server:
    volumes:
      - ./data:/data
EOF

# Restart with persistent storage
docker-compose down && docker-compose up -d
```

### Deployment Checklist

1. **✅ HTTPS Setup**: Modern clients require HTTPS in production
2. **✅ Persistent Storage**: Mount `/data` volume to preserve users/collections
3. **✅ User Creation**: Add users with proper collection path parameter
4. **✅ Container Health**: Verify container starts without auth table errors
5. **✅ Client Testing**: Test full sync cycle including media files
6. **✅ Log Monitoring**: Watch for authentication and sync success messages

### Common Error Patterns

| Error | Cause | Solution |
|-------|-------|----------|
| `Exception: expected auth` | Discovery request not returning HTTP 400 | Update authentication flow in `sync_app.py` |
| `missing original_size` | Missing `anki-original-size` header | Ensure all responses return `(body, size)` tuples |
| `Authentication failed for nonexistent user` | User not in database | Create user with proper collection path |
| `30-second timeout` | Blocking read on chunked requests | Implement non-blocking chunked parsing |
| `no such table: auth` | Database not initialized | Auto-create database schema on startup |
| `error sending request for url ()` | Self-signed certificate rejected by client | Use proper SSL certificate or add to system trust store |

## 🔧 Deployment Configuration

### Environment Variables

The server supports the following environment variables for production deployment:

| Variable | Default | Description |
|----------|---------|-------------|
| `DOMAIN_NAME` | `localhost` | Your domain name for SSL certificates |
| `EMAIL` | - | Email for Let's Encrypt certificate registration |
| `ANKI_SYNC_SERVER_HOST` | `anki-sync-server` | Internal hostname of sync server |
| `ANKI_SYNC_SERVER_PORT` | `27702` | Internal port of sync server |
| `HTTPS_CERT_PATH` | `/app/certs` | Path to SSL certificates |
| `ANKISYNCD_DATA_ROOT` | `/app/collections` | Path to collections storage |
| `ANKISYNCD_AUTH_DB_PATH` | `/app/collections/auth.db` | Path to user database |

### Volume Mounts

**Critical**: Collections are stored in `/app/collections/users/` inside the container.

```yaml
volumes:
  # Correct collection mount
  - ./data/collections:/app/collections
  
  # Certificate storage
  - ./certs:/app/certs:ro
  
  # Let's Encrypt challenge
  - ./certbot/www:/var/www/certbot:ro
```

### SSL Certificate Handling

The HTTPS proxy automatically detects and uses certificates in this priority order:

1. **Let's Encrypt**: `{cert_path}/{domain_name}.crt` and `{domain_name}.key`
2. **Self-signed**: `{cert_path}/localhost+3.pem` and `localhost+3-key.pem`

For production, use the AWS deployment script which handles Let's Encrypt automatically.

### Production Monitoring

```bash
# Monitor sync activity
docker logs anki-sync-server -f | grep -E "(SUCCESS|ERROR|Authentication)"

# Check for deprecation warnings (cosmetic only)
docker logs anki-sync-server 2>&1 | grep "deprecated"

# Verify user database
docker exec anki-sync-server python -c "
from ankisyncd.users.sqlite_manager import SqliteUserManager
mgr = SqliteUserManager('/data/auth.db', '/data/collections')
print('Users:', mgr.user_list())
"
```

---

## Extending & Hacking
* Swap in your own **user manager** (`users/`) for OAuth or LDAP auth.
* Emit **Prometheus metrics** by wrapping the ASGI app with middleware.
* Plug a remote filesystem or S3 into `media_manager.py`—paths are abstracted through a single interface.

Pull requests welcome; see `CONTRIBUTING.md` for guidelines.

---

## License
Released under the **GNU AGPL-v3+**.  
Copyright © the respective contributors.
