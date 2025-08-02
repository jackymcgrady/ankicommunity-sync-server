#!/bin/bash

# AWS Lightsail Deployment Script for Anki Sync Server
# This script sets up the Anki sync server with automatic SSL certificates

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Starting AWS Lightsail deployment...${NC}"

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo -e "${RED}❌ This script should not be run as root${NC}"
   exit 1
fi

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠️  .env file not found. Creating from template...${NC}"
    cp env.production.example .env
    echo -e "${RED}❌ Please edit .env file with your domain and email, then run this script again${NC}"
    exit 1
fi

# Load environment variables
source .env

# Validate required variables
if [ -z "$DOMAIN_NAME" ] || [ -z "$EMAIL" ]; then
    echo -e "${RED}❌ DOMAIN_NAME and EMAIL must be set in .env file${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Configuration loaded:${NC}"
echo -e "   Domain: ${DOMAIN_NAME}"
echo -e "   Email: ${EMAIL}"

# Create necessary directories
echo -e "${GREEN}📁 Creating directories...${NC}"
mkdir -p data/collections
mkdir -p certs
mkdir -p certbot/conf
mkdir -p certbot/www
mkdir -p logs

# Set proper permissions
chmod 755 data/collections
chmod 755 certs
chmod 755 certbot/www

# Stop any existing containers
echo -e "${GREEN}🛑 Stopping existing containers...${NC}"
docker-compose -f docker-compose.prod.yml down --remove-orphans || true

# Build images
echo -e "${GREEN}🔨 Building Docker images...${NC}"
docker-compose -f docker-compose.prod.yml build

# Start HTTP server first for certificate challenge
echo -e "${GREEN}🌐 Starting HTTP server for certificate challenge...${NC}"
docker-compose -f docker-compose.prod.yml up -d anki-https-proxy

# Wait for HTTP server to be ready
echo -e "${GREEN}⏳ Waiting for HTTP server to be ready...${NC}"
sleep 10

# Test if domain resolves to this server
echo -e "${GREEN}🔍 Testing domain resolution...${NC}"
DOMAIN_IP=$(nslookup $DOMAIN_NAME | grep -A1 "Name:" | tail -1 | awk '{print $2}' || echo "")
SERVER_IP=$(curl -s http://checkip.amazonaws.com/ || echo "")

if [ "$DOMAIN_IP" != "$SERVER_IP" ]; then
    echo -e "${YELLOW}⚠️  Warning: Domain $DOMAIN_NAME resolves to $DOMAIN_IP but server IP is $SERVER_IP${NC}"
    echo -e "${YELLOW}   Make sure your DNS A record points to this server${NC}"
fi

# Generate SSL certificate
echo -e "${GREEN}🔐 Generating SSL certificate...${NC}"
docker-compose -f docker-compose.prod.yml run --rm certbot

# Check if certificate was generated successfully
if [ ! -f "certbot/conf/live/$DOMAIN_NAME/fullchain.pem" ]; then
    echo -e "${RED}❌ Certificate generation failed${NC}"
    echo -e "${YELLOW}   Falling back to self-signed certificate...${NC}"
    
    # Generate self-signed certificate as fallback
    openssl req -x509 -newkey rsa:4096 -keyout "certs/$DOMAIN_NAME.key" \
        -out "certs/$DOMAIN_NAME.crt" -days 365 -nodes \
        -subj "/C=US/ST=State/L=City/O=AnkiSyncServer/CN=$DOMAIN_NAME"
    
    echo -e "${YELLOW}⚠️  Self-signed certificate generated. HTTPS will show security warnings.${NC}"
else
    echo -e "${GREEN}✅ SSL certificate generated successfully${NC}"
fi

# Restart all services
echo -e "${GREEN}🔄 Starting all services...${NC}"
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d

# Wait for services to be ready
echo -e "${GREEN}⏳ Waiting for services to start...${NC}"
sleep 15

# Test HTTP endpoint
echo -e "${GREEN}🧪 Testing HTTP endpoint...${NC}"
if curl -f -s http://localhost:27702/sync/hostKey > /dev/null; then
    echo -e "${GREEN}✅ HTTP endpoint is working${NC}"
else
    echo -e "${RED}❌ HTTP endpoint test failed${NC}"
fi

# Test HTTPS endpoint
echo -e "${GREEN}🧪 Testing HTTPS endpoint...${NC}"
if curl -k -f -s https://localhost:27703/ > /dev/null; then
    echo -e "${GREEN}✅ HTTPS endpoint is working${NC}"
else
    echo -e "${RED}❌ HTTPS endpoint test failed${NC}"
fi

# Show service status
echo -e "${GREEN}📊 Service status:${NC}"
docker-compose -f docker-compose.prod.yml ps

# Show connection information
echo -e "${GREEN}🎉 Deployment completed!${NC}"
echo -e ""
echo -e "${GREEN}Connection Information:${NC}"
echo -e "   HTTP:  http://$DOMAIN_NAME:27702"
echo -e "   HTTPS: https://$DOMAIN_NAME:27703"
echo -e ""
echo -e "${GREEN}Next steps:${NC}"
echo -e "1. Create a user: python3 add_email_user.py"
echo -e "2. Configure Anki client with: https://$DOMAIN_NAME:27703"
echo -e "3. Monitor logs: docker-compose -f docker-compose.prod.yml logs -f"
echo -e ""
echo -e "${YELLOW}Note: If using self-signed certificate, Anki will show a security warning on first connection.${NC}" 