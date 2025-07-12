#!/bin/bash

# SSL Certificate Setup Script for Anki Sync Server
# Usage: ./scripts/setup-https-certs.sh [mode]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}[SSL]${NC} $1"
}

# Parse command line arguments
MODE="${1:-self-signed}"

print_header "Setting up SSL certificates - Mode: $MODE"

# Change to project directory
cd "$PROJECT_DIR"

# Create certs directory
mkdir -p certs

case "$MODE" in
    "self-signed")
        print_status "Generating self-signed SSL certificate..."
        
        if [ -f certs/server.crt ] && [ -f certs/server.key ]; then
            print_warning "SSL certificates already exist. Use 'force' to overwrite."
            exit 0
        fi
        
        # Generate self-signed certificate
        openssl req -x509 -newkey rsa:4096 -keyout certs/server.key -out certs/server.crt -days 365 -nodes \
            -subj "/C=US/ST=State/L=City/O=AnkiSyncServer/CN=localhost" \
            -addext "subjectAltName=DNS:localhost,DNS:*.localhost,IP:127.0.0.1,IP:::1"
        
        chmod 600 certs/server.key
        chmod 644 certs/server.crt
        
        print_status "Self-signed certificate generated successfully"
        print_status "Certificate: $(pwd)/certs/server.crt"
        print_status "Private key: $(pwd)/certs/server.key"
        print_status "Valid for: 365 days"
        
        # Show certificate info
        openssl x509 -in certs/server.crt -text -noout | grep -E "(Subject:|Not After|DNS:|IP:)"
        ;;
    
    "letsencrypt")
        print_status "Setting up Let's Encrypt certificate..."
        
        # Check if certbot is installed
        if ! command -v certbot &> /dev/null; then
            print_error "Certbot is not installed. Please install it first:"
            echo "  Ubuntu/Debian: sudo apt install certbot"
            echo "  CentOS/RHEL: sudo yum install certbot"
            echo "  macOS: brew install certbot"
            exit 1
        fi
        
        # Prompt for domain
        read -p "Enter your domain name: " DOMAIN
        
        if [ -z "$DOMAIN" ]; then
            print_error "Domain name is required"
            exit 1
        fi
        
        print_status "Obtaining Let's Encrypt certificate for $DOMAIN..."
        
        # Use certbot to obtain certificate
        # Note: This requires domain validation and port 80 access
        sudo certbot certonly --standalone --preferred-challenges http -d "$DOMAIN"
        
        # Copy certificates to our certs directory
        sudo cp "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" certs/server.crt
        sudo cp "/etc/letsencrypt/live/$DOMAIN/privkey.pem" certs/server.key
        
        # Fix permissions
        sudo chown $USER:$USER certs/server.crt certs/server.key
        chmod 644 certs/server.crt
        chmod 600 certs/server.key
        
        print_status "Let's Encrypt certificate installed successfully"
        print_status "Certificate: $(pwd)/certs/server.crt"
        print_status "Private key: $(pwd)/certs/server.key"
        
        # Set up auto-renewal reminder
        print_warning "Remember to set up auto-renewal with: sudo crontab -e"
        print_warning "Add this line: 0 12 * * * /usr/bin/certbot renew --quiet"
        ;;
    
    "custom")
        print_status "Setting up custom SSL certificate..."
        
        print_status "Please place your SSL certificate files in the certs/ directory:"
        print_status "  - Certificate: certs/server.crt"
        print_status "  - Private key: certs/server.key"
        
        if [ -f certs/server.crt ] && [ -f certs/server.key ]; then
            print_status "Custom certificates found and ready to use"
            
            # Verify certificate format
            if openssl x509 -in certs/server.crt -text -noout > /dev/null 2>&1; then
                print_status "Certificate format is valid"
            else
                print_error "Certificate format is invalid"
                exit 1
            fi
            
            # Verify private key format
            if openssl rsa -in certs/server.key -check -noout > /dev/null 2>&1; then
                print_status "Private key format is valid"
            else
                print_error "Private key format is invalid"
                exit 1
            fi
            
            # Set correct permissions
            chmod 644 certs/server.crt
            chmod 600 certs/server.key
            
        else
            print_error "Certificate files not found"
            exit 1
        fi
        ;;
    
    "force")
        print_status "Forcing regeneration of self-signed certificate..."
        
        # Remove existing certificates
        rm -f certs/server.crt certs/server.key
        
        # Generate new self-signed certificate
        openssl req -x509 -newkey rsa:4096 -keyout certs/server.key -out certs/server.crt -days 365 -nodes \
            -subj "/C=US/ST=State/L=City/O=AnkiSyncServer/CN=localhost" \
            -addext "subjectAltName=DNS:localhost,DNS:*.localhost,IP:127.0.0.1,IP:::1"
        
        chmod 600 certs/server.key
        chmod 644 certs/server.crt
        
        print_status "Certificate regenerated successfully"
        ;;
    
    "info")
        print_status "SSL certificate information:"
        
        if [ -f certs/server.crt ]; then
            print_status "Certificate found: $(pwd)/certs/server.crt"
            openssl x509 -in certs/server.crt -text -noout | grep -E "(Subject:|Issuer:|Not Before|Not After|DNS:|IP:)"
        else
            print_warning "No certificate found"
        fi
        
        if [ -f certs/server.key ]; then
            print_status "Private key found: $(pwd)/certs/server.key"
        else
            print_warning "No private key found"
        fi
        ;;
    
    "help"|*)
        echo "SSL Certificate Setup Script for Anki Sync Server"
        echo ""
        echo "Usage: $0 [mode]"
        echo ""
        echo "Modes:"
        echo "  self-signed    Generate self-signed certificate for development/testing"
        echo "  letsencrypt    Obtain Let's Encrypt certificate for production"
        echo "  custom         Use custom SSL certificate files"
        echo "  force          Force regeneration of self-signed certificate"
        echo "  info           Show certificate information"
        echo "  help           Show this help message"
        echo ""
        echo "Examples:"
        echo "  $0 self-signed     # Generate self-signed cert for development"
        echo "  $0 letsencrypt     # Get Let's Encrypt cert for production"
        echo "  $0 custom          # Use your own certificate files"
        echo "  $0 info            # Show current certificate info"
        echo ""
        echo "Note: For production, use either letsencrypt or custom certificates."
        echo "      Self-signed certificates will show security warnings in browsers."
        ;;
esac 