# Anki Sync Server

A modern, open-source implementation of Anki's v2.1.57+ sync protocol.  
If you manage multiple Anki clients (desktop, mobile, web) and need a **self-hosted** alternative to AnkiWeb, this server keeps every device in lock-step—collections, media, and change history included.

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
| `ANKISYNCD_AUTH_DB_PATH` | Auth backend (when using SQLite) | `./users.db` |
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
# User Management - Create persistent auth database
docker exec anki-sync-server python -c "
from ankisyncd.users.sqlite_manager import SqliteUserManager
mgr = SqliteUserManager('/data/auth.db', '/data/collections')
mgr.add_user('your-email@example.com', 'your-password')
print('User added successfully')
"

# Verify user authentication
docker exec anki-sync-server python -c "
from ankisyncd.users.sqlite_manager import SqliteUserManager
mgr = SqliteUserManager('/data/auth.db', '/data/collections')
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
