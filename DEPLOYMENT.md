# Deployment Guide

## Quick Start with AWS Cognito

### 1. Clone and Configure

```bash
git clone https://github.com/ankicommunity/anki-sync-server.git
cd anki-sync-server
```

### 2. Set up AWS Cognito Authentication

```bash
# Copy example files
cp env.cognito.example .env
cp docker-compose.cognito.example.yml docker-compose.cognito.yml

# Edit .env with your actual AWS Cognito credentials
# Edit docker-compose.cognito.yml with your domain and certificate paths
```

### 3. Configure Environment Variables

Edit `.env` and set:
- `ANKISYNCD_COGNITO_USER_POOL_ID`: Your Cognito User Pool ID
- `ANKISYNCD_COGNITO_CLIENT_ID`: Your Cognito App Client ID  
- `ANKISYNCD_COGNITO_CLIENT_SECRET`: Your Cognito App Client Secret
- `ANKISYNCD_COGNITO_REGION`: Your AWS region
- `AWS_ACCESS_KEY_ID`: Your AWS Access Key
- `AWS_SECRET_ACCESS_KEY`: Your AWS Secret Key

### 4. Deploy

```bash
# Build and start containers
docker-compose -f docker-compose.cognito.yml up -d

# Check status
docker-compose -f docker-compose.cognito.yml ps
```

### 5. Configure Anki Clients

Users should configure their Anki clients with:
- **Sync Server**: `https://your-domain.com` (no port needed)
- **Username**: Their Cognito username, email, or phone
- **Password**: Their Cognito password

## Security Notes

- Never commit `.env` or files with real credentials
- Use IAM roles instead of access keys when possible
- Rotate credentials regularly
- Monitor AWS CloudTrail for authentication events

## SSL Certificates

Place your SSL certificates in the `certs/` directory:
- `your-domain.com.crt`
- `your-domain.com.key`

## Troubleshooting

### Check Logs
```bash
docker logs anki-sync-server-cognito
docker logs anki-https-proxy-cognito
```

### Test Authentication
```bash
curl -k -X POST https://your-domain.com/sync/hostKey \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "password": "testpass"}'
```

For detailed setup instructions, see [COGNITO_SETUP.md](COGNITO_SETUP.md).