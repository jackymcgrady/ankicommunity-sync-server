#!/bin/bash
set -e

# Configuration
DOMAIN="sync.ankipi.com"
EMAIL="${EMAIL:-your-email@example.com}"
COMPOSE_FILE="docker-compose.nginx.yml"

echo "🚀 Setting up Anki Sync Server with nginx and Let's Encrypt SSL"
echo "Domain: $DOMAIN"
echo "Email: $EMAIL"

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p letsencrypt/live/$DOMAIN
mkdir -p certbot-www
mkdir -p logs/nginx
mkdir -p logs/certbot
mkdir -p data/collections

# Start nginx with self-signed certificates first
echo "🔧 Starting nginx with self-signed certificates..."
docker-compose -f $COMPOSE_FILE up -d nginx anki-sync-server

# Wait for nginx to be ready
echo "⏳ Waiting for nginx to be ready..."
sleep 10

# Check if we should get real certificates
if [ "$EMAIL" != "your-email@example.com" ] && [ -n "$EMAIL" ]; then
    echo "🔒 Obtaining Let's Encrypt SSL certificate..."
    
    # Get SSL certificate
    docker-compose -f $COMPOSE_FILE run --rm certbot certonly \
        --webroot \
        --webroot-path=/var/www/certbot \
        --email $EMAIL \
        --agree-tos \
        --no-eff-email \
        -d $DOMAIN
    
    if [ $? -eq 0 ]; then
        echo "✅ SSL certificate obtained successfully!"
        echo "🔄 Reloading nginx with new certificate..."
        docker-compose -f $COMPOSE_FILE exec nginx nginx -s reload
    else
        echo "❌ Failed to obtain SSL certificate. Continuing with self-signed..."
    fi
else
    echo "⚠️  Using self-signed certificates. Set EMAIL environment variable for Let's Encrypt."
fi

echo ""
echo "🎉 Setup complete!"
echo ""
echo "📊 Container status:"
docker-compose -f $COMPOSE_FILE ps
echo ""
echo "🌐 Access your Anki sync server at:"
echo "   https://$DOMAIN"
echo ""
echo "📝 To view logs:"
echo "   docker-compose -f $COMPOSE_FILE logs -f"
echo ""
echo "🔧 To manage SSL certificates:"
echo "   docker-compose -f $COMPOSE_FILE --profile certbot run --rm certbot renew"
echo ""

# Set up automatic certificate renewal
echo "⏰ Setting up automatic certificate renewal..."
cat > renew-certs.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
docker-compose -f docker-compose.nginx.yml --profile certbot run --rm certbot renew
docker-compose -f docker-compose.nginx.yml exec nginx nginx -s reload
EOF

chmod +x renew-certs.sh

echo "✅ Created renew-certs.sh for certificate renewal"
echo "   Add this to your crontab: 0 12 * * * /path/to/renew-certs.sh"