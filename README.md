# Anki Sync Server

Self-hosted Anki sync server with AWS Cognito authentication and automatic HTTPS certificates.

## Quick Start

```bash
# Configure environment
cp .env.example .env && nano .env     # fill in AWS + Cognito + domain

# Launch server
docker-compose -f docker-compose.latest.yml up -d

# Verify
curl -k https://<your-domain>/sync/hostKey   # should return JSON
```

Connect Anki clients to `https://<your-domain>`.

## Configuration

Required environment variables:

| Variable | Purpose |
|----------|---------|
| AWS_ACCESS_KEY_ID | AWS credentials for Cognito |
| AWS_SECRET_ACCESS_KEY | AWS credentials for Cognito |
| ANKISYNCD_COGNITO_USER_POOL_ID | Cognito User Pool ID |
| ANKISYNCD_COGNITO_CLIENT_ID | Cognito App Client ID |
| ANKISYNCD_COGNITO_CLIENT_SECRET | Cognito App Client Secret |
| DOMAIN_NAME | Your domain name |
| EMAIL | Email for Let's Encrypt certificates |

## Operations

```bash
# Start/stop
docker-compose -f docker-compose.latest.yml up -d
docker-compose -f docker-compose.latest.yml down

# View logs
docker-compose -f docker-compose.latest.yml logs -f anki-sync-server

# Reset user collection (if sync issues)
echo "yes" | python3 scripts/reset_user_collection.py <username> --confirm --data-root ./efs
```

Important: User data is stored in `./efs/` directory (EFS mount).

## Troubleshooting

**Sync stuck or failing?**
```bash
# Reset user data
echo "yes" | python3 scripts/reset_user_collection.py <username> --confirm --data-root ./efs
docker-compose -f docker-compose.latest.yml restart anki-sync-server
```

**Check logs:**
```bash
docker-compose -f docker-compose.latest.yml logs anki-sync-server
```

**Disk space issues?**
```bash
docker system prune -a -f  # Clean up unused Docker data
```
