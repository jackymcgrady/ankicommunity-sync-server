#!/bin/sh
set -e

# Set defaults for environment variables
export DOMAIN_NAME=${DOMAIN_NAME:-localhost}
export SSL_MODE=${SSL_MODE:-self-signed}
export DEV_MODE=${DEV_MODE:-false}
export ANKI_SYNC_SERVER_HOST=${ANKI_SYNC_SERVER_HOST:-anki-sync-server-nginx}
export ANKI_SYNC_SERVER_PORT=${ANKI_SYNC_SERVER_PORT:-27702}
export MAX_BODY_SIZE=${MAX_BODY_SIZE:-2G}
export PROXY_CONNECT_TIMEOUT=${PROXY_CONNECT_TIMEOUT:-60s}
export PROXY_SEND_TIMEOUT=${PROXY_SEND_TIMEOUT:-300s}
export PROXY_READ_TIMEOUT=${PROXY_READ_TIMEOUT:-300s}

# Set SSL certificate paths based on domain
export SSL_CERT_PATH="/etc/letsencrypt/live/${DOMAIN_NAME}/fullchain.pem"
export SSL_KEY_PATH="/etc/letsencrypt/live/${DOMAIN_NAME}/privkey.pem"

# Configure HTTP/2 and proxy settings based on environment
if [ "$DEV_MODE" = "true" ]; then
    export HTTP2_CONFIG=""
    export PROXY_HTTP_VERSION="proxy_http_version 1.1;"
else
    export HTTP2_CONFIG="http2 on;"
    export PROXY_HTTP_VERSION=""
fi

# Handle SSL certificate generation based on SSL_MODE
if [ "$SSL_MODE" = "self-signed" ] && [ ! -f "$SSL_CERT_PATH" ]; then
    echo "Creating self-signed SSL certificates for $DOMAIN_NAME..."
    mkdir -p "/etc/letsencrypt/live/${DOMAIN_NAME}"
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout "$SSL_KEY_PATH" \
        -out "$SSL_CERT_PATH" \
        -subj "/C=US/ST=State/L=City/O=Development/CN=${DOMAIN_NAME}" \
        -addext "subjectAltName=DNS:${DOMAIN_NAME},IP:127.0.0.1"
elif [ "$SSL_MODE" = "letsencrypt" ] && [ ! -f "$SSL_CERT_PATH" ]; then
    echo "Let's Encrypt certificates should be generated externally"
    echo "Use: docker-compose run --rm certbot certonly --webroot --webroot-path=/var/www/certbot --email ${EMAIL} --agree-tos --no-eff-email -d ${DOMAIN_NAME}"
fi

# Generate nginx config
cat > /etc/nginx/conf.d/server.conf << EOF
# HTTP to HTTPS redirect
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN_NAME};
    
    # Let's Encrypt ACME challenge
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
EOF

# Add HTTP sync endpoints for development mode
if [ "$DEV_MODE" = "true" ]; then
    cat >> /etc/nginx/conf.d/server.conf << EOF
    
    # Allow sync endpoints over HTTP for development
    location /sync/ {
        proxy_pass http://${ANKI_SYNC_SERVER_HOST}:${ANKI_SYNC_SERVER_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_buffering off;
        proxy_cache off;
        proxy_connect_timeout ${PROXY_CONNECT_TIMEOUT};
        proxy_send_timeout ${PROXY_SEND_TIMEOUT};
        proxy_read_timeout ${PROXY_READ_TIMEOUT};
    }
    
    location /msync/ {
        proxy_pass http://${ANKI_SYNC_SERVER_HOST}:${ANKI_SYNC_SERVER_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_buffering off;
        proxy_cache off;
        proxy_connect_timeout ${PROXY_CONNECT_TIMEOUT};
        proxy_send_timeout ${PROXY_SEND_TIMEOUT};
        proxy_read_timeout ${PROXY_READ_TIMEOUT};
    }
EOF
fi

cat >> /etc/nginx/conf.d/server.conf << EOF
    
    # Redirect all other HTTP traffic to HTTPS
    location / {
        return 301 https://\$server_name\$request_uri;
    }
}

# HTTPS configuration
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    ${HTTP2_CONFIG}
    server_name ${DOMAIN_NAME};

    # SSL configuration
    ssl_certificate ${SSL_CERT_PATH};
    ssl_certificate_key ${SSL_KEY_PATH};
    
    # SSL protocols and ciphers - Anki client compatible
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    
    # Force HTTP/1.1 for Anki client compatibility (if needed)
    ${PROXY_HTTP_VERSION}
    
    # SSL session cache
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Increase client max body size for large Anki collections
    client_max_body_size ${MAX_BODY_SIZE};
    
    # Proxy settings for Anki sync server
    location / {
        proxy_pass http://${ANKI_SYNC_SERVER_HOST}:${ANKI_SYNC_SERVER_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # Disable proxy buffering for real-time sync
        proxy_buffering off;
        proxy_cache off;
        
        # Timeout settings for large syncs
        proxy_connect_timeout ${PROXY_CONNECT_TIMEOUT};
        proxy_send_timeout ${PROXY_SEND_TIMEOUT};
        proxy_read_timeout ${PROXY_READ_TIMEOUT};
    }
    
    # Health check endpoint
    location /health {
        access_log off;
        return 200 "healthy\\n";
        add_header Content-Type text/plain;
    }
}
EOF

echo "Generated nginx configuration for domain: $DOMAIN_NAME"