# HTTPS Setup for Anki Sync Server

## Current Setup

### 1. HTTP Server (ankisyncd)
- **Port**: 27702
- **URL**: http://localhost:27702
- **Status**: ✅ Working with modern protocol support

### 2. HTTPS Proxy
- **Port**: 27703  
- **URL**: https://localhost:27703
- **Certificate**: Trusted local certificate via mkcert
- **Status**: ✅ Working - forwards requests to HTTP server

### 3. Authentication
- **Username**: test
- **Password**: test123
- **Database**: ./auth.db

## How to Start

1. **Start HTTP Server**:
   ```bash
   python3 -m ankisyncd src/ankisyncd.conf
   ```

2. **Start HTTPS Proxy**:
   ```bash
   python3 https_proxy.py
   ```

## Client Configuration

Configure your Anki client to use:
- **Sync Server URL**: `https://localhost:27703`
- **Username**: `test`
- **Password**: `test123`

## Testing

Test the setup with:
```bash
python3 test_https_client.py
```

## Technical Details

- **Modern Protocol Support**: ✅ 
  - Zstd compression
  - JSON request/response format
  - anki-sync headers (v11)
  
- **SSL/TLS**: ✅
  - mkcert generated certificates
  - Trusted for localhost, 127.0.0.1, ::1
  
- **Proxy Features**: ✅
  - HTTP → HTTPS translation
  - Header forwarding
  - Request/response logging

## Why This Works

The issue with Anki client sending empty request bodies over HTTP appears to be related to security policies in modern browsers/clients that refuse to send credentials over insecure connections. By providing HTTPS with a trusted certificate, the client should now send the full authentication data.

## Next Steps

If this resolves the empty request body issue, the client should successfully authenticate and proceed with normal sync operations. 