# Anki Sync Server

A production-ready, self-hosted implementation of Anki's sync protocol with AWS Cognito authentication and HTTPS support.  
If you manage multiple Anki clients (desktop, mobile, web) and need a **secure alternative** to AnkiWeb, this server keeps every device in perfect sync—collections, media, and review history included.

## ✅ Production Status

**WORKING FEATURES:**
- ✅ **HTTPS connectivity** via `https://sync.ankipi.com`
- ✅ **AWS Cognito authentication** with username-based collection folders
- ✅ **Fast media sync** - thousands of files sync swiftly
- ✅ **Modern Anki client compatibility** (v25.02+)
- ✅ **Docker deployment** with automatic SSL/TLS termination

## 🚀 Quick Start

### Production Deployment (nginx + Let's Encrypt)
```bash
# 1. Configure your domain and email
export EMAIL="your-email@example.com"
export DOMAIN_NAME="sync.ankipi.com"

# 2. Run automated setup with SSL
./scripts/setup-nginx-ssl.sh

# 3. Verify services are running
docker-compose -f docker-compose.nginx.yml ps

# 4. Users authenticate via Cognito - no manual user creation needed
# Connect Anki to: https://sync.ankipi.com
```

### Alternative: Quick Start (Self-signed SSL)
```bash
# For testing or internal use with self-signed certificates
docker-compose -f docker-compose.nginx.yml up -d

# Connect Anki to: https://yourdomain.com (accept SSL warning)
```

### Local Development
```bash
# Clone and start with Docker
git clone https://github.com/jackymcgrady/ankicommunity-sync-server.git
cd ankicommunity-sync-server

# Start with HTTPS proxy
docker-compose up -d

# Connect Anki to: https://localhost:27703
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
| `collection/` | SQLite collection wrapper with schema upgrades |
| `media_manager.py` | Deduplicates, normalizes, and streams media files |
| `users/cognito_manager.py` | **AWS Cognito authentication** with username-based collections |
| `https_proxy.py` | **Custom HTTPS proxy** with SSL termination and Anki protocol optimization |

Each component is **loosely coupled** for easy customization and monitoring integration.

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

### AWS Cognito Authentication
The server integrates with AWS Cognito User Pools for secure authentication:

| Environment Variable | Purpose | Example |
| ------------------- | ------- | ------- |
| `COGNITO_USER_POOL_ID` | AWS Cognito User Pool ID | `us-east-1_ABC123DEF` |
| `COGNITO_CLIENT_ID` | App client ID | `1a2b3c4d5e6f7g8h9i0j` |
| `COGNITO_CLIENT_SECRET` | App client secret (optional) | `secret123...` |
| `COGNITO_REGION` | AWS region | `us-east-1` |

### Core Server Settings
| Env Var | Purpose | Default |
| ------- | ------- | ------- |
| `ANKISYNCD_HOST` | Bind address | `0.0.0.0` |
| `ANKISYNCD_PORT` | TCP port | `27702` |
| `ANKISYNCD_DATA_ROOT` | Collections storage | `/app/collections` |
| `ANKISYNCD_LOG_LEVEL` | `DEBUG` / `INFO` | `INFO` |

### HTTPS Proxy Settings
| Env Var | Purpose | Default |
| ------- | ------- | ------- |
| `DOMAIN_NAME` | Your domain name for SSL certificates | `localhost` |
| `ANKI_SERVER_HOST` | Internal sync server hostname | `anki-sync-server` |
| `ANKI_SERVER_PORT` | Internal sync server port | `27702` |

---

## Architecture Overview

### Production Architecture (nginx-based)
```
[Anki Client] → [Port 443/HTTPS] → [nginx Reverse Proxy] → [Port 27702/HTTP] → [Sync Server] → [AWS Cognito]
                                           ↓ SSL Termination
                                    [anki-nginx-proxy]         [anki-sync-server-nginx]
```

### nginx HTTPS Implementation

**nginx Reverse Proxy** (`Dockerfile.nginx`):
- **Technology**: Production-grade nginx with Alpine Linux
- **SSL Management**: Automatic Let's Encrypt certificates via certbot
- **Features**:
  - HTTP/2 enabled for performance
  - Strong SSL cipher suites (TLS 1.2/1.3)
  - Security headers (HSTS, X-Frame-Options, etc.)
  - Large file uploads (2GB max for collections)
  - Real-time proxy (buffering disabled)

**Why nginx**:
- ✅ **Production proven** - battle-tested reverse proxy
- ✅ **Performance** - efficient handling of HTTPS/HTTP/2
- ✅ **SSL automation** - integrated Let's Encrypt support
- ✅ **Security** - comprehensive security headers and configurations
- ✅ **Monitoring** - detailed access/error logs

**Certificate Management**:
```bash
# Automatic Let's Encrypt certificates
./scripts/setup-nginx-ssl.sh  # Initial setup
./renew-certs.sh              # Renewal (add to crontab)

# Self-signed fallback for development
docker-compose -f docker-compose.nginx.yml up -d
```

**AWS Cognito Integration**:
- Collection folders: `/data/collections/users/{cognito_username}/`
- Session caching reduces API calls  
- Supports multiple auth flows (`USER_PASSWORD_AUTH`, `ADMIN_NO_SRP_AUTH`)

---

## 🔐 User Management with AWS Cognito

### No Manual User Creation Required
Users authenticate directly against your AWS Cognito User Pool:
1. **Create Cognito User Pool** in AWS Console
2. **Add users** via AWS Console, CLI, or registration flow
3. **Configure** Docker Compose with Cognito credentials
4. **Users log in** with their Cognito email/password

### Cognito User Pool Setup
```bash
# Example AWS CLI commands for setting up Cognito
aws cognito-idp create-user-pool --pool-name "anki-sync-users"
aws cognito-idp create-user-pool-client --user-pool-id "us-east-1_ABC123" --client-name "anki-sync-client"

# Add users
aws cognito-idp admin-create-user --user-pool-id "us-east-1_ABC123" --username "user@example.com" --message-action SUPPRESS
aws cognito-idp admin-set-user-password --user-pool-id "us-east-1_ABC123" --username "user@example.com" --password "TempPassword123!" --permanent
```

### Collection Directory Structure
When users authenticate, collections are automatically organized by Cognito username:
```
/app/collections/users/
├── john.doe/           # Cognito username (not email)
│   ├── collection.anki2
│   └── collection.media/
└── jane.smith/
    ├── collection.anki2
    └── collection.media/
```

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

### nginx-based Production Setup (Recommended)
```bash
# Setup with automatic Let's Encrypt SSL
export EMAIL="your-email@example.com"
./scripts/setup-nginx-ssl.sh

# Verify services are running
docker-compose -f docker-compose.nginx.yml ps
# Should show:
# - anki-nginx-proxy (ports 80:80, 443:443)
# - anki-sync-server-nginx (internal port 27702)
```

### Docker Compose Files Available
- `docker-compose.nginx.yml` - **Recommended**: nginx + Let's Encrypt SSL
- `docker-compose.cognito.yml` - Legacy: Custom Python HTTPS proxy  
- `docker-compose.yml` - Base development configuration

### Essential Commands

```bash
# Production deployment with nginx + SSL
docker-compose -f docker-compose.nginx.yml up -d

# View logs
docker-compose -f docker-compose.nginx.yml logs -f nginx
docker-compose -f docker-compose.nginx.yml logs -f anki-sync-server

# Monitor sync activity
docker logs anki-sync-server-nginx 2>&1 | grep -E "(Authentication|SUCCESS|ERROR)"

# nginx access logs (sync requests)
docker exec anki-nginx-proxy tail -f /var/log/nginx/access.log

# Container shell access
docker exec -it anki-sync-server-nginx bash

# SSL certificate renewal
./renew-certs.sh

# Stop services
docker-compose -f docker-compose.nginx.yml down
```

### Volume Mounts (Critical for Data Persistence)
```yaml
volumes:
  # Collections storage - MUST persist across restarts
  - ./data:/data
  
  # Let's Encrypt SSL certificates
  - ./letsencrypt:/etc/letsencrypt:rw
  
  # Web root for ACME challenge
  - ./certbot-www:/var/www/certbot:rw
  
  # nginx logs
  - ./logs/nginx:/var/log/nginx
```

### Container Architecture
```
anki-nginx-proxy        (ports 80:80, 443:443)
    ↓ nginx reverse proxy ↓
anki-sync-server-nginx  (internal port 27702)
    ↓ authenticates via ↓  
AWS Cognito User Pool
    ↓ stores collections in ↓
./data/collections/users/{cognito_username}/
```

### Health Monitoring & SSL Management
```bash
# Check container health
docker-compose -f docker-compose.nginx.yml ps

# Monitor nginx access logs
docker exec anki-nginx-proxy tail -f /var/log/nginx/access.log

# Check SSL certificate status
docker exec anki-nginx-proxy openssl x509 -in /etc/letsencrypt/live/sync.ankipi.com/fullchain.pem -text -noout | grep -E "(Subject|Not After)"

# Renew SSL certificates (setup as cron job)
0 12 * * * cd /path/to/project && ./renew-certs.sh

# Monitor resource usage
docker stats anki-nginx-proxy anki-sync-server-nginx
```

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

## 🔧 Production Configuration

### Required Environment Variables (docker-compose.cognito.yml)
```yaml
environment:
  # AWS Cognito Settings
  COGNITO_USER_POOL_ID: "us-east-1_ABC123DEF"    # Your Cognito User Pool ID
  COGNITO_CLIENT_ID: "1a2b3c4d5e6f7g8h9i0j"      # Your App Client ID
  COGNITO_CLIENT_SECRET: "your-client-secret"      # Optional: App Client Secret
  COGNITO_REGION: "us-east-1"                     # AWS Region
  
  # Server Configuration
  ANKISYNCD_HOST: "0.0.0.0"
  ANKISYNCD_PORT: "27702"
  ANKISYNCD_DATA_ROOT: "/app/collections"
  
  # HTTPS Proxy Settings
  DOMAIN_NAME: "yourdomain.com"                   # Your actual domain
  ANKI_SERVER_HOST: "anki-sync-server-cognito"   # Internal container name
  ANKI_SERVER_PORT: "27702"                      # Internal sync server port
```

### SSL Certificate Management
The HTTPS proxy (`https_proxy.py`) automatically handles SSL certificates:

1. **Checks for Let's Encrypt**: `/app/certs/{domain}.crt` and `{domain}.key`
2. **Falls back to self-signed**: `/app/certs/localhost+3.pem` and `localhost+3-key.pem`
3. **Serves HTTPS on port 27703**

### Critical Volume Mounts
```yaml
volumes:
  # MUST mount collections for data persistence
  - ./data/collections:/app/collections
  
  # Optional: External SSL certificates
  - ./certs:/app/certs:ro
```

### Production Monitoring
```bash
# Monitor authentication events
docker logs anki-sync-server-cognito 2>&1 | grep "Authentication"

# Check sync operations
docker logs anki-sync-server-cognito 2>&1 | grep -E "(sync|SUCCESS|ERROR)"

# View collection structure
docker exec anki-sync-server-cognito ls -la /app/collections/users/

# Check Cognito connectivity
docker exec anki-sync-server-cognito python3 -c "
import boto3
client = boto3.client('cognito-idp', region_name='us-east-1')
print('Cognito connection: OK')
"
```

### Security Considerations
- **Cognito credentials** stored as environment variables (not in code)
- **Collection isolation** by username prevents user data crossover
- **HTTPS enforcement** ensures encrypted client-server communication
- **No local auth database** reduces attack surface

---

## Extending & Customization

### Authentication Backends
The current implementation uses AWS Cognito (`cognito_manager.py`), but the architecture supports:
* **Custom OAuth providers** - implement new manager in `users/`
* **LDAP integration** - extend base authentication manager
* **Multi-tenant auth** - add organization-based user isolation

### Monitoring Integration
* **Prometheus metrics** - wrap ASGI app with metrics middleware
* **Logging enhancements** - structured logging for sync operations
* **Health checks** - extend container health monitoring

### Storage Customization
* **S3 media storage** - replace local filesystem in `media_manager.py`
* **Database clustering** - distribute collections across multiple nodes
* **Backup automation** - implement automated collection backups

### Performance Optimization
* **Redis session caching** - replace in-memory Cognito session cache
* **CDN integration** - serve media files through CDN
* **Load balancing** - scale sync servers horizontally

---

## Project Status

**✅ PRODUCTION READY**
- Successfully deployed at `https://sync.ankipi.com`
- Handles thousands of media files efficiently
- Secure AWS Cognito authentication
- Modern Anki client compatibility (v25.02+)
- Docker deployment with HTTPS termination

**🔧 CONFIGURATION REQUIRED**
- AWS Cognito User Pool setup
- Domain name and SSL certificates
- Docker Compose environment variables

---

## License
Released under the **GNU AGPL-v3+**.  
Copyright © the respective contributors.
