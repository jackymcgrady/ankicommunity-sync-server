# Anki Sync Server

A modern, compatible sync server for Anki that supports the latest protocol (>=2.1.57). Still under development, with only Anki Mac Client being tested against.

## Features

✅ **Full Protocol Support**
- Compatible with Anki Desktop >=2.1.57
- Full sync protocol implementation
- Complete media sync support
- Efficient batch processing
- WAL mode for better concurrency

✅ **Media Management**
- Proper media file handling
- Efficient media deletions
- Batch media transfers
- File integrity checks
- Cross-platform filename normalization

✅ **Reliability**
- Proper SQLite WAL handling
- Transaction safety
- Conflict resolution
- Automatic schema updates
- Comprehensive error handling

## Quick Start

1. Install dependencies:
```bash
pip install -r src/requirements.txt
pip install -e src
```

2. Configure the server:
```bash
cp src/ankisyncd.conf src/ankisyncd/.
```

3. Create a user:
```bash
python -m ankisyncd_cli adduser <username>
```

4. Start the server:
```bash
python -m ankisyncd
```

## HTTPS Setup

For production use, set up HTTPS using a reverse proxy like Nginx:

```nginx
server {
    listen 443 ssl;
    server_name your.domain.com;

    ssl_certificate /path/to/fullchain.pem;
    ssl_certificate_key /path/to/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:27701/;
        proxy_http_version 1.0;
        client_max_body_size 222M;
    }
}
```

## Client Configuration

### Anki Desktop (>=2.1.57)

In preference - syncing, fill in your sync server address:port

### AnkiDroid (not yet tested)

In AnkiDroid settings:
1. Advanced → Custom sync server
2. Set Sync URL: `http://your.server:27701`
3. Set Media Sync URL: `http://your.server:27701/msync`

## Important Notes

### Database Management
- Never manually delete SQLite WAL files
- Always use proper checkpointing:
```bash
sqlite3 collection.anki2 "PRAGMA wal_checkpoint(TRUNCATE);"
```

### Files Using WAL Mode
- Collection databases: `collection.anki2`
- Media databases: `collection.media.db`, `collection.media.server.db`
- Session database: `session.db`

### Logging Configuration
- Default: One log line per sync attempt with timing
- Format: `✅ SYNC SUCCESS` or `❌ SYNC FAILED` with details
- Debug mode: Change `stdlib_logging.INFO` to `stdlib_logging.DEBUG` in logger.py

## Directory Structure

```
collections/
└── users/
    └── username/
        ├── collection.anki2
        ├── collection.media/
        ├── collection.media.db
        └── collection.media.server.db
```

## Development

### Testing
```bash
make init    # Install dependencies
make tests   # Run test suite
```

### Configuration
Use environment variables (preferred) or config file:
- Environment variables: Prefix with `ANKISYNCD_` (e.g., `ANKISYNCD_AUTH_DB_PATH`)
- Config file: `ankisyncd.conf`

## License

GNU AGPL v3 or later. See [LICENSE](LICENSE) for details.
