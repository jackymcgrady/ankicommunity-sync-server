# Deployment Findings & Optimizations

This document summarizes key findings from local testing and optimizations made for AWS production deployment.

## 🔍 Key Issues Discovered

### 1. Collection Storage Path
- **Issue**: Volume mount was incorrect (`/data/collections` vs actual `/app/collections`)
- **Root Cause**: Server stores collections in `/app/collections/users/` internally
- **Fix**: Updated volume mapping to `./data/collections:/app/collections`
- **Impact**: Collections now properly accessible on host machine

### 2. HTTPS Certificate Validation
- **Issue**: Anki client shows "error sending request for url ()" with self-signed certificates
- **Root Cause**: Anki uses `reqwest` library which strictly validates SSL certificates
- **Analysis**: Client-side code examination revealed modern HTTP clients reject self-signed certs
- **Fix**: Implemented automatic Let's Encrypt certificate generation for production
- **Fallback**: Self-signed certificates with system trust store addition

### 3. HTTPS Proxy Configuration
- **Issue**: `NameError` with undefined `anki_port` variable in proxy
- **Root Cause**: Variable scope issue in HTTPS proxy handler
- **Fix**: Added environment variable support and proper class variable handling
- **Improvement**: Dynamic certificate detection (Let's Encrypt vs mkcert)

### 4. Environment Variable Management
- **Issue**: Hardcoded configuration values throughout codebase
- **Fix**: Comprehensive environment variable support
- **Added Variables**:
  - `DOMAIN_NAME`: For SSL certificate generation
  - `EMAIL`: For Let's Encrypt registration
  - `ANKI_SYNC_SERVER_HOST/PORT`: Internal service communication
  - `HTTPS_CERT_PATH`: Certificate location
  - `ANKISYNCD_DATA_ROOT`: Collections storage path

## 🚀 Production Optimizations

### Docker Configuration
- **Simplified**: Removed complex monitoring and nginx services for core functionality
- **Health Checks**: Added proper health checks for both HTTP and HTTPS services
- **Certificate Management**: Integrated certbot service for automatic SSL renewal
- **Volume Optimization**: Proper persistent storage for collections and certificates

### Deployment Automation
- **AWS Script**: Created `scripts/aws-deploy.sh` for one-command deployment
- **Environment Template**: Added `env.production.example` for easy configuration
- **DNS Validation**: Automatic domain resolution checking
- **Fallback Strategy**: Self-signed certificates if Let's Encrypt fails

### Security Improvements
- **SSL/TLS**: Modern cipher suites and TLS 1.2+ enforcement
- **Certificate Priority**: Let's Encrypt preferred, self-signed as fallback
- **Port Configuration**: Proper internal/external port mapping
- **HTTP Challenge**: Built-in support for Let's Encrypt HTTP-01 validation

## 📋 Deployment Checklist

### Pre-deployment
- [ ] Domain DNS pointing to server IP
- [ ] Ports 80, 27702, 27703 open in firewall
- [ ] Docker and docker-compose installed
- [ ] Environment file configured

### Deployment Steps
1. **Clone repository**: From main branch with latest fixes
2. **Configure environment**: Copy and edit `.env` file
3. **Run deployment script**: `./scripts/aws-deploy.sh`
4. **Verify services**: Check HTTP and HTTPS endpoints
5. **Create users**: Use `add_email_user.py`
6. **Test sync**: Connect Anki client and perform full sync

### Post-deployment
- [ ] Monitor logs for authentication success
- [ ] Test media sync functionality
- [ ] Verify certificate auto-renewal
- [ ] Set up log rotation and monitoring

## 🔧 Technical Architecture

### Service Communication
```
Anki Client → HTTPS Proxy (27703) → Sync Server (27702)
                    ↓
              Certificate Files
                    ↓
              Let's Encrypt/Self-signed
```

### Data Flow
1. **Client Request**: HTTPS to proxy on port 27703
2. **Certificate Validation**: Automatic cert detection and loading
3. **Proxy Forward**: HTTP to sync server on port 27702
4. **Response Processing**: Zstd compression and header management
5. **Client Response**: HTTPS response with proper headers

### Storage Layout
```
data/
├── collections/
│   ├── auth.db                    # User authentication
│   └── users/
│       └── user@example.com/      # User collections
certs/
├── domain.crt                     # Let's Encrypt certificate
├── domain.key                     # Private key
└── localhost+3.pem               # Fallback self-signed
certbot/
├── conf/                          # Let's Encrypt configuration
└── www/                           # HTTP challenge files
```

## 🐛 Troubleshooting Guide

### Certificate Issues
- **Let's Encrypt Fails**: Check DNS resolution and port 80 accessibility
- **Self-signed Warnings**: Expected behavior, client will show security warning
- **Certificate Not Found**: Verify volume mounts and file permissions

### Connection Issues
- **HTTP Works, HTTPS Fails**: Certificate or proxy configuration problem
- **Both Fail**: Check service status and logs
- **Intermittent Failures**: Often certificate validation timing issues

### Client-side Issues
- **"error sending request"**: Certificate validation failure
- **Authentication Errors**: User not created or wrong credentials
- **Sync Timeouts**: Network or server performance issues

## 📈 Performance Considerations

### Resource Requirements
- **Minimum**: 1GB RAM, 1 CPU core, 10GB storage
- **Recommended**: 2GB RAM, 2 CPU cores, 50GB storage
- **Scaling**: Horizontal scaling possible with shared storage

### Optimization Opportunities
- **Database**: SQLite WAL mode for better concurrency
- **Caching**: Media file caching for faster transfers
- **Compression**: Zstd compression reduces bandwidth usage
- **Monitoring**: Prometheus/Grafana for production monitoring

This document serves as a reference for future deployments and troubleshooting. 