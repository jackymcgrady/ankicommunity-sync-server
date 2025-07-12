# Docker Guide for Anki Sync Server

This guide covers the complete Docker setup for the Anki Sync Server, including development, GitHub Actions CI/CD, and production deployment.

## Overview

The Docker setup provides:
- **Multi-stage Dockerfile** for development and production
- **Docker Compose** for local development
- **GitHub Actions** for automated builds
- **Production deployment** scripts
- **HTTPS proxy** support
- **Monitoring** with Prometheus and Grafana (optional)

## Quick Start

### 1. Local Development

```bash
# Build and start development environment
./scripts/docker-dev.sh build
./scripts/docker-dev.sh up

# View logs
./scripts/docker-dev.sh logs

# Access shell
./scripts/docker-dev.sh shell

# Run tests
./scripts/docker-dev.sh test
```

Your server will be available at `http://localhost:27701`.

### 2. Production Testing

```bash
# Test production build locally
./scripts/docker-dev.sh prod
```

Server will be available at `http://localhost:27702`.

### 3. HTTPS Setup

```bash
# Generate SSL certificates
./scripts/docker-dev.sh certs

# Start with HTTPS proxy
./scripts/docker-dev.sh https
```

- HTTP server will be available at `http://localhost:27701`
- HTTPS server will be available at `https://localhost:27703`

## Development Workflow

### Local Development

1. **Start Development Environment**
   ```bash
   ./scripts/docker-dev.sh up
   ```

2. **Code Changes**
   - Edit code on your Mac
   - Changes are automatically reflected in the container via volume mounts
   - No need to rebuild for code changes

3. **Testing**
   ```bash
   ./scripts/docker-dev.sh test
   ```

4. **Debugging**
   ```bash
   ./scripts/docker-dev.sh shell
   ./scripts/docker-dev.sh logs
   ```

### Available Commands

| Command | Description |
|---------|-------------|
| `build` | Build Docker images |
| `up` | Start development environment |
| `down` | Stop development environment |
| `restart` | Restart development environment |
| `logs` | Show container logs |
| `shell` | Open shell in container |
| `test` | Run tests in container |
| `clean` | Clean up Docker resources |
| `prod` | Start production environment |
| `https` | Start with HTTPS proxy |
| `status` | Show container status |

## GitHub Actions CI/CD

### Setup

1. **Enable GitHub Actions**
   - Actions are automatically enabled when you push to `main` or `develop` branches

2. **GitHub Container Registry**
   - Images are automatically published to `ghcr.io/yourusername/your-repo-name`
   - No additional setup required for public repositories

3. **Environment Variables**
   - `GITHUB_TOKEN` is automatically provided
   - No secrets need to be configured for basic setup

### Workflow Triggers

- **Push to main/develop**: Builds and pushes `latest` tag
- **Tags (v*)**: Builds and pushes version tags
- **Pull Requests**: Builds but doesn't push (testing)

### Image Tags

- `latest` - Latest main branch
- `develop` - Latest develop branch
- `v2.4.0` - Specific version tags
- `sha-abcdef` - Specific commit SHA

## Production Deployment

### Server Setup

1. **Install Docker and Docker Compose**
   ```bash
   # Ubuntu/Debian
   sudo apt update
   sudo apt install -y docker.io docker-compose
   sudo systemctl enable docker
   sudo usermod -aG docker $USER
   ```

2. **Clone Repository**
   ```bash
   git clone https://github.com/jackymcgrady/ankicommunity-sync-server.git
   cd ankicommunity-sync-server
   ```

3. **Setup Environment**
   ```bash
   # Copy environment file
   cp .env.example .env
   
   # Edit configuration
   nano .env
   
   # Create data directories
   mkdir -p data logs certs backups
   ```

### Deployment Commands

```bash
# Deploy to staging
./scripts/docker-deploy.sh staging

# Deploy specific version to production
./scripts/docker-deploy.sh production v2.4.0

# Deploy latest to production
./scripts/docker-deploy.sh production latest

# Force pull and deploy
./scripts/docker-deploy.sh production latest true

# Check deployment status
./scripts/docker-deploy.sh status

# View logs
./scripts/docker-deploy.sh logs

# Rollback to previous version
./scripts/docker-deploy.sh rollback
```

### Deployment Process

1. **Backup**: Current data is backed up to `./backups/`
2. **Pull**: Latest images are pulled from registry
3. **Stop**: Existing containers are stopped
4. **Start**: New containers are started
5. **Verify**: Health checks ensure deployment success
6. **Cleanup**: Old images are cleaned up

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and customize:

```bash
# Core Configuration
REGISTRY=ghcr.io
IMAGE_NAME=yourusername/your-repo-name
TAG=latest

# Application Settings
ANKISYNCD_CONFIG_PATH=/app/ankisyncd.conf
PYTHONUNBUFFERED=1
TZ=UTC

# HTTPS Settings
HTTPS_PORT=27702

# Monitoring (optional)
GRAFANA_PASSWORD=your_secure_password
```

### Docker Compose Profiles

- **Default**: Basic development setup
- **Production**: Production-ready containers
- **HTTPS**: Includes HTTPS proxy
- **Nginx**: Includes nginx reverse proxy
- **Monitoring**: Includes Prometheus and Grafana

```bash
# Use specific profile
docker-compose --profile production up -d
docker-compose --profile monitoring up -d
```

## Monitoring (Optional)

### Enable Monitoring

```bash
# Start with monitoring
docker-compose --profile monitoring up -d
```

### Access Monitoring

- **Prometheus**: `http://localhost:9090`
- **Grafana**: `http://localhost:3000` (admin/admin)

### Monitoring Features

- Container health and resource usage
- Application metrics
- Custom dashboards
- Alerting (can be configured)

## SSL/HTTPS Setup

### 1. Generate Certificates

**For Development (Self-signed):**
```bash
# Quick setup
./scripts/docker-dev.sh certs

# Or use the dedicated script
./scripts/setup-https-certs.sh self-signed
```

**For Production (Let's Encrypt):**
```bash
# Install certbot first, then:
./scripts/setup-https-certs.sh letsencrypt
```

**For Production (Custom Certificate):**
```bash
# Place your certificates in the certs/ directory:
# - certs/server.crt (certificate)
# - certs/server.key (private key)
./scripts/setup-https-certs.sh custom
```

### 2. Configure HTTPS

**Development:**
```bash
# Start with HTTPS proxy
./scripts/docker-dev.sh https

# Access at:
# - HTTP: http://localhost:27701
# - HTTPS: https://localhost:27703
```

**Production:**
```bash
# Production deployment uses HTTPS by default
./scripts/docker-deploy.sh production latest

# Access at:
# - HTTPS: https://your-domain.com (port 443)
# - HTTPS: https://your-domain.com:27703 (alternative port)
```

### 3. Certificate Management

```bash
# Check certificate info
./scripts/setup-https-certs.sh info

# Regenerate certificate
./scripts/setup-https-certs.sh force

# Get help
./scripts/setup-https-certs.sh help
```

### 4. Production HTTPS Considerations

**Port Configuration:**
- Port 443: Standard HTTPS port (requires root/sudo or port forwarding)
- Port 27703: Alternative HTTPS port (no special privileges needed)

**Certificate Types:**
- **Self-signed**: For development/testing only (browser warnings)
- **Let's Encrypt**: Free certificates for production (auto-renewal needed)
- **Custom**: Your own certificates (commercial CA or internal CA)

**Security Best Practices:**
- Use strong cipher suites
- Enable HSTS headers
- Set up proper firewall rules
- Regular certificate renewal
- Monitor certificate expiration

## Troubleshooting

### Common Issues

1. **Port Conflicts**
   ```bash
   # Check what's using ports
   sudo lsof -i :27701
   sudo lsof -i :27702
   ```

2. **Permission Issues**
   ```bash
   # Fix data directory permissions
   sudo chown -R $USER:$USER data/ logs/ certs/
   ```

3. **Container Won't Start**
   ```bash
   # Check logs
   docker-compose logs anki-sync-server
   
   # Check health
   docker ps
   ```

4. **Image Pull Failures**
   ```bash
   # Login to registry
   docker login ghcr.io
   
   # Pull manually
   docker pull ghcr.io/yourusername/your-repo-name:latest
   ```

### Debug Commands

```bash
# View all containers
docker ps -a

# View logs
docker logs anki-sync-server-prod

# Execute commands in container
docker exec -it anki-sync-server-prod bash

# View container stats
docker stats

# Inspect container
docker inspect anki-sync-server-prod
```

## Best Practices

### Development

1. **Use volume mounts** for active development
2. **Keep containers stateless** - data in volumes
3. **Use proper logging** - structured logs
4. **Test in production mode** before deploying

### Production

1. **Regular backups** before deployments
2. **Use specific image tags** not `latest`
3. **Monitor resource usage** 
4. **Set up proper SSL certificates**
5. **Use secrets management** for sensitive data
6. **Regular security updates**

### Security

1. **Don't expose unnecessary ports**
2. **Use non-root users** in containers
3. **Scan images** for vulnerabilities
4. **Keep base images updated**
5. **Use secrets** for sensitive configuration

## Integration with Development Workflow

### Recommended Workflow

1. **Develop on Mac**
   ```bash
   # Start development environment
   ./scripts/docker-dev.sh up
   
   # Make changes to code
   # Test changes automatically reflect
   
   # Run tests
   ./scripts/docker-dev.sh test
   ```

2. **Commit and Push**
   ```bash
   git add .
   git commit -m "Add new feature"
   git push origin develop
   ```

3. **GitHub Actions**
   - Automatically builds and tests
   - Publishes Docker images
   - Runs security scans

4. **Deploy to Server**
   ```bash
   # On your server
   ./scripts/docker-deploy.sh production latest
   ```

This provides a complete development-to-production pipeline using Docker! 