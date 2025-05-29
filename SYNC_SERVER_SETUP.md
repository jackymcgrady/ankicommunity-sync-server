# Anki Sync Server Local Setup Guide

## Section 1: HTTP/HTTPS Setup and Authentication

### Overview

This guide documents the successful setup of a local Anki sync server compatible with modern Anki clients (version 25.02.5+). The implementation includes both HTTP and HTTPS support, proper authentication handling, and modern protocol compatibility.

### Architecture

The setup consists of two components:
1. **HTTP Sync Server** (port 27702) - Core ankisyncd implementation
2. **HTTPS Proxy** (port 27703) - TLS termination and protocol handling

```
Anki Client → HTTPS Proxy (27703) → HTTP Server (27702)
             [TLS + Protocol]      [Core Logic]
```

### HTTP Server (ankisyncd)

#### Configuration
- **Port**: 27702
- **Binding**: 0.0.0.0 (all interfaces)
- **Protocol**: HTTP/1.1
- **Content-Type**: application/octet-stream
- **Compression**: Zstandard (zstd)

#### Key Features
- Modern Anki sync protocol (v11) support
- Zstd request/response compression
- JSON-based request handling
- SQLite user authentication database
- Dynamic schema detection and compatibility

### HTTPS Proxy Implementation

#### SSL/TLS Configuration
```python
# Modern TLS settings for compatibility
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.minimum_version = ssl.TLSVersion.TLSv1_2
context.maximum_version = ssl.TLSVersion.TLSv1_3
context.set_ciphers('ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:...')
context.options |= ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1
context.options |= ssl.OP_CIPHER_SERVER_PREFERENCE
```

#### Certificate Setup
- **Tool**: mkcert (for trusted local certificates)
- **Domains**: localhost, 127.0.0.1, ::1
- **Files**: `localhost+2.pem`, `localhost+2-key.pem`

```bash
# Generate certificates
mkcert localhost 127.0.0.1 ::1
```

#### Protocol Handling
The proxy handles several critical protocol requirements:

1. **Header Processing**: Extracts and forwards `anki-sync` headers
2. **Content Compression**: Handles zstd compression/decompression
3. **Transfer Encoding**: Supports both chunked and Content-Length requests
4. **Original Size Header**: Adds `anki-original-size` header for media sync

### Authentication System

#### Database Structure
- **File**: `auth.db` (SQLite database)
- **Table**: `auth(username VARCHAR PRIMARY KEY, hash VARCHAR)`
- **Hashing**: MD5 (for compatibility with legacy clients)

#### Supported Login Formats

✅ **Username Authentication**
```json
{"u": "test", "p": "test123"}
```

✅ **Email Authentication**  
```json
{"u": "test@example.com", "p": "test123"}
```

#### User Creation
```python
import hashlib
import sqlite3

# Create auth database
conn = sqlite3.connect('auth.db')
conn.execute('''CREATE TABLE IF NOT EXISTS auth 
                (username VARCHAR PRIMARY KEY, hash VARCHAR)''')

# Add username-based user
username = "test"
password = "test123"
hash_value = hashlib.md5(password.encode()).hexdigest()
conn.execute("INSERT OR REPLACE INTO auth VALUES (?, ?)", (username, hash_value))

# Add email-based user
email = "test@example.com"
hash_value = hashlib.md5(password.encode()).hexdigest()
conn.execute("INSERT OR REPLACE INTO auth VALUES (?, ?)", (email, hash_value))

conn.commit()
conn.close()
```

### Starting the Servers

#### 1. Start HTTP Server
```bash
python3 -m ankisyncd &
```

#### 2. Start HTTPS Proxy
```bash
python3 https_proxy.py
```

### Client Configuration

#### Anki Desktop Settings
1. Open Anki → Preferences → Syncing
2. Set sync server URL to: `https://localhost:27703`
3. Use credentials: `test` / `test123` or `test@example.com` / `test123`

### Authentication Flow

1. **Initial Request**: Client sends empty `/sync/hostKey` request
2. **401 Response**: Server returns 401 to trigger authentication
3. **Credentials**: Client sends compressed JSON with username/password
4. **Validation**: Server validates against SQLite auth database
5. **Host Key**: Server returns encrypted host key for session
6. **Session**: Subsequent requests use host key for authorization

### Troubleshooting Authentication

#### Common Issues

**"Network error occurred"**
- Check HTTPS proxy is running on port 27703
- Verify certificates are properly installed
- Ensure both servers are running

**"403 Forbidden"**
- Authentication succeeded but session validation failed
- Check host key generation and session management

**"Invalid credentials"**
- Verify user exists in auth.db
- Check password hash is correct MD5
- Ensure username/email format matches database

#### Debug Logging
The server provides detailed logging for authentication:
```
[INFO] Authentication successful for user: 'test', returning host key
[INFO] Extracted credentials - identifier: 'test', password present: True
```

### Future Login Reliability

#### Ensuring Consistent Access

1. **Persistent Database**: Keep `auth.db` file in version control or backup
2. **Certificate Renewal**: Monitor certificate expiration (mkcert certs are valid for years)
3. **Service Management**: Consider using systemd or launchd for automatic startup
4. **Port Consistency**: Document port assignments to avoid conflicts

#### Adding New Users
```bash
# Using ankisyncd_cli (if available)
python3 -m ankisyncd_cli adduser newuser newpassword

# Or direct database insertion
sqlite3 auth.db "INSERT OR REPLACE INTO auth VALUES ('newuser', '$(echo -n 'newpassword' | md5sum | cut -d' ' -f1)');"
```

### Status: Working Components ✅

- ✅ HTTPS proxy with modern TLS
- ✅ HTTP server on port 27702  
- ✅ Username authentication (`test`/`test123`)
- ✅ Email authentication (`test@example.com`/`test123`)
- ✅ Protocol v11 compatibility
- ✅ Zstd compression handling
- ✅ Host key generation and exchange
- ✅ Certificate-based HTTPS

### Next Steps

The authentication and basic protocol handling are working. The next phase involves:
1. Resolving schema compatibility issues
2. Implementing collection metadata exchange
3. Supporting full sync operations
4. Adding media sync capabilities

---

*Last updated: 2025-01-29* 