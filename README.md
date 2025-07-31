# Anki Sync Server

A production-ready, self-hosted implementation of Anki's sync protocol with AWS Cognito authentication and HTTPS support.  
If you manage multiple Anki clients (desktop, mobile, web) and need a **secure alternative** to AnkiWeb, this server keeps every device in perfect sync—collections, media, and review history included.

## ✅ Production Status

**BATTLE-TESTED FEATURES:**
- ✅ **Robust collection sync** with intelligent conflict resolution and database integrity protection
- ✅ **HTTPS connectivity** with automatic SSL certificates via nginx reverse proxy
- ✅ **AWS Cognito authentication** with secure username-based collection isolation
- ✅ **Efficient media sync** - differential sync handles thousands of files with minimal data transfer
- ✅ **Modern Anki client compatibility** (v25.02+) with full protocol compliance
- ✅ **Docker deployment** with production-grade nginx SSL termination and monitoring
- ✅ **Crash recovery** - media databases survive server restarts, collections auto-restore from uploads

## 🚀 Quick Start

### Production Deployment (nginx + Let's Encrypt)
```bash
# 1. Configure environment variables for security
cp .env.example .env
# Edit .env with your AWS credentials and Cognito settings

# 2. Deploy with secure environment variables
docker-compose -f docker-compose.latest.yml up -d

# 3. Verify services are running
docker-compose -f docker-compose.latest.yml ps

# 4. Users authenticate via Cognito - no manual user creation needed
# Connect Anki to: https://your-domain.com
```

### ⚠️ SECURITY SETUP REQUIRED
**CRITICAL**: Never commit AWS credentials to git. Use environment variables:
```bash
# Required environment variables (set in .env file):
AWS_ACCESS_KEY_ID=your_access_key_here
AWS_SECRET_ACCESS_KEY=your_secret_key_here
ANKISYNCD_COGNITO_USER_POOL_ID=your_user_pool_id
ANKISYNCD_COGNITO_CLIENT_ID=your_client_id
ANKISYNCD_COGNITO_CLIENT_SECRET=your_client_secret
DOMAIN_NAME=your-domain.com
EMAIL=your-email@example.com
```

### Local Development
```bash
# Clone and configure
git clone https://github.com/your-username/ankicommunity-sync-server.git
cd ankicommunity-sync-server

# Setup environment variables
cp .env.example .env
# Edit .env with your credentials

# Start with secure configuration
docker-compose -f docker-compose.latest.yml up -d

# Connect Anki to: https://your-domain.com
```

---

## The User Story
1. **Edit Anywhere** – Study on your phone during the commute, then refine cards on your laptop at night.
2. **Hit *Sync*** – Each client contacts the same endpoint (`/sync`) over HTTPS and authenticates with your credentials.
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
* **Automatic schema migrations** keep legacy clients functional across versions 11-18.
* **Conflict resolution** follows upstream Anki logic (newer `mod` wins, deterministic tie-breakers).
* **Locked writes** ensure two devices never overwrite each other's work mid-sync.
* **Crash resilience** - separated storage for collections and media enables recovery from server failures.
* **Differential media sync** - only transfers changed files using USN tracking, not full collections.
* **Schema compatibility** - robust fallback mechanisms handle corrupted or missing collection databases.

---

## Configuration

### ⚠️ Security-First Configuration
**CRITICAL**: Use `.env` file for all credentials. Never commit secrets to git.

### Required Environment Variables
Copy `.env.example` to `.env` and configure:

| Environment Variable | Purpose | Required |
| ------------------- | ------- | -------- |
| `AWS_ACCESS_KEY_ID` | AWS access key | ✅ Required |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key | ✅ Required |
| `ANKISYNCD_COGNITO_USER_POOL_ID` | Cognito User Pool ID | ✅ Required |
| `ANKISYNCD_COGNITO_CLIENT_ID` | Cognito App client ID | ✅ Required |
| `ANKISYNCD_COGNITO_CLIENT_SECRET` | Cognito client secret | ✅ Required |
| `ANKISYNCD_COGNITO_REGION` | AWS region | ✅ Required |
| `DOMAIN_NAME` | Your domain for SSL certificates | ✅ Required |
| `EMAIL` | Email for Let's Encrypt | ✅ Required |

### Optional Configuration
| Env Var | Purpose | Default |
| ------- | ------- | ------- |
| `AWS_DEFAULT_REGION` | AWS region fallback | `ap-southeast-1` |
| `SSL_MODE` | SSL certificate mode | `letsencrypt` |
| `DEV_MODE` | Development mode | `false` |

### Quick Setup Commands
```bash
# 1. Clone and configure
git clone https://github.com/your-username/ankicommunity-sync-server.git
cd ankicommunity-sync-server

# 2. Setup environment (REQUIRED)
cp .env.example .env
nano .env  # Add your AWS/Cognito credentials

# 3. Deploy
docker-compose -f docker-compose.latest.yml up -d

# 4. Verify
docker ps  # Should show both containers running
curl -k https://localhost/sync/hostKey  # Test endpoint
```

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
./scripts/setup-https-certs.sh letsencrypt

# Self-signed fallback for development
./scripts/setup-https-certs.sh self-signed

# Certificate info
./scripts/setup-https-certs.sh info
```

**AWS Cognito Integration**:
- Collection folders: `/data/collections/users/{cognito_username}/`
- Session caching reduces API calls  
- Supports multiple auth flows (`USER_PASSWORD_AUTH`, `ADMIN_NO_SRP_AUTH`)

---

## 🔐 AWS Cognito Authentication

### Prerequisites
1. **AWS Account** with IAM access key and secret
2. **Cognito User Pool** with App Client configured
3. **Environment variables** configured in `.env` file

### AWS Setup
```bash
# Get your Cognito configuration from AWS Console:
# 1. Go to Amazon Cognito → User pools
# 2. Select your user pool
# 3. Note the User pool ID
# 4. Go to App integration → App clients
# 5. Note Client ID and Client secret

# Add to your .env file:
ANKISYNCD_COGNITO_USER_POOL_ID=your_user_pool_id
ANKISYNCD_COGNITO_CLIENT_ID=your_client_id  
ANKISYNCD_COGNITO_CLIENT_SECRET=your_client_secret
```

### Collection Directory Structure
When users authenticate, collections are automatically organized by Cognito username:
```
/data/collections/users/
├── john.doe/           # Cognito username (not email)
│   ├── collection.anki2
│   └── collection.media/
└── jane.smith/
    ├── collection.anki2
    └── collection.media/
```

---

## 🐳 Docker Deployment

### nginx-based Production Setup (Recommended)
**Image Size**: Optimized production setup

```bash
# 1. Configure environment variables (REQUIRED)
cp .env.example .env
nano .env  # Add your AWS credentials and Cognito settings

# 2. Deploy with secure configuration
docker-compose -f docker-compose.latest.yml up -d

# 3. Verify services are running
docker-compose -f docker-compose.latest.yml ps
# Should show:
# - anki-nginx-proxy (ports 80:80, 443:443)  
# - anki-sync-server (internal port 27702)
```

### Security Features
- **Environment Variables**: All credentials use secure env vars (never committed)
- **Non-root Containers**: Enhanced security with dedicated user accounts
- **SSL/TLS**: Production-grade HTTPS with nginx reverse proxy

### Essential Commands

```bash
# Production deployment with nginx + SSL
docker-compose -f docker-compose.latest.yml up -d

# View logs
docker-compose -f docker-compose.latest.yml logs -f nginx
docker-compose -f docker-compose.latest.yml logs -f anki-sync-server

# Monitor sync activity
docker logs anki-sync-server-nginx 2>&1 | grep -E "(Authentication|SUCCESS|ERROR)"

# nginx access logs (sync requests)
docker exec anki-nginx-proxy tail -f /var/log/nginx/access.log

# Container shell access
docker exec -it anki-sync-server-nginx bash

# Stop services
docker-compose -f docker-compose.latest.yml down
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

---

## 🔧 Scripts and Deployment Automation

The project includes several deployment and management scripts:

### Available Scripts
- **`scripts/aws-deploy.sh`** - Full AWS deployment with SSL certificates
- **`scripts/docker-deploy.sh`** - Production deployment with registry management
- **`scripts/docker-dev.sh`** - Development environment management
- **`scripts/generate-nginx-config.sh`** - Dynamic nginx configuration generation
- **`scripts/setup-https-certs.sh`** - SSL certificate management (Let's Encrypt, self-signed, custom)

### Usage Examples
```bash
# Generate SSL certificates
./scripts/setup-https-certs.sh letsencrypt
./scripts/setup-https-certs.sh self-signed

# Development environment
./scripts/docker-dev.sh build
./scripts/docker-dev.sh up

# Production deployment
./scripts/docker-deploy.sh production latest
```

---

## 🐛 Troubleshooting & Debugging

### Modern Anki Client Compatibility (v25.02+)

**Key Fixes Implemented:**

#### 1. Authentication Flow Issues
- **Issue**: Client discovery requests weren't triggering authentication dialogs
- **Fix**: Return HTTP 400 "expected auth" for discovery requests (`{"k": ""}` with empty body)

#### 2. Missing anki-original-size Header
- **Issue**: All zstd-compressed responses must include `anki-original-size` header with uncompressed byte count
- **Fix**: Updated response handling to include proper size headers

#### 3. Request Body Parsing for Streaming Clients
- **Issue**: Modern clients stream request bodies without `Content-Length` headers using chunked transfer encoding
- **Fix**: Enhanced request parsing to handle chunked transfer encoding and missing content-length headers

### Common Error Patterns & Solutions

| Error | Cause | Solution |
|-------|-------|----------|
| `Exception: expected auth` | Discovery request not returning HTTP 400 | Update authentication flow in `sync_app.py` |
| `missing original_size` | Missing `anki-original-size` header | Ensure all responses return proper size headers |
| `Authentication failed` | User not in Cognito | Verify AWS Cognito configuration |
| `SSL certificate error` | Self-signed certificate rejected | Use Let's Encrypt or add cert to trust store |
| `NoneType object has no attribute 'scalar'` | Collection database corrupted/missing | Server auto-recovers with schema fallback; client uploads restore collection |
| Server reports "no collections" but has media | Database inconsistency after crash | Normal - media databases survive restarts; collection upload restores sync |
| Quick sync with thousands of media files | Efficient differential sync working correctly | Expected behavior - only transfers changed files (USN-based) |

### Quick Recovery Commands
```bash
# Stop everything and rebuild
docker-compose -f docker-compose.latest.yml down
docker-compose -f docker-compose.latest.yml up --build -d

# Check container status
docker ps
docker logs anki-sync-server-nginx --tail 10
docker logs anki-nginx-proxy --tail 10

# Test connectivity
curl -k https://localhost/sync/hostKey
```

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

## Project Status & Reliability

**✅ PRODUCTION READY & BATTLE-TESTED**
- Secure AWS Cognito authentication with session caching
- Modern Anki client compatibility (v25.02+) with full protocol compliance  
- Docker deployment with nginx HTTPS termination and Let's Encrypt automation
- Crash-resilient architecture with separated collection/media storage
- Differential media sync handles thousands of files efficiently
- Robust schema compatibility across Anki versions 11-18
- Comprehensive error recovery and database integrity protection

**🔧 CONFIGURATION REQUIRED**
- AWS Cognito User Pool setup with proper IAM permissions
- Domain name registration and DNS configuration
- Docker Compose environment variables (.env file setup)
- SSL certificate management (automated via Let's Encrypt)

**🧠 SANITY PRESERVATION METHOD**
To maintain clarity while implementing complex sync protocols and crash recovery mechanisms, this codebase follows a principle of **"explain the why, not just the what"** in both logging and documentation. Every non-trivial operation includes context about what problem it solves, particularly around edge cases like orphaned media databases, schema detection failures, and differential sync optimizations. The extensive logging helps trace exactly what happened during sync issues, making debugging straightforward rather than archeological.

---

## License
Released under the **GNU AGPL-v3+**.  
Copyright © the respective contributors.