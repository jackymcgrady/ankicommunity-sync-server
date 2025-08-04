# Anki Sync Server Scripts

This directory contains utility scripts for managing the Anki sync server.

## User Collection Reset Script

The `reset_user_collection.py` script provides a safe way to completely reset a user's collection and media data, giving them a clean slate for sync operations.

### Use Cases

- **Debugging sync issues**: Reset a user's data to eliminate any corrupted state
- **Testing sync functionality**: Provide a clean environment for testing
- **Resolving persistent conflicts**: Start fresh when sync conflicts cannot be resolved
- **Development and troubleshooting**: Reset test users during development

### Safety Features

- **Dry run by default**: Shows what would be deleted without making changes
- **Confirmation required**: Must use `--confirm` flag to actually perform reset
- **Detailed analysis**: Shows current data before reset
- **Comprehensive logging**: Detailed logging of all operations
- **Error handling**: Graceful error handling with detailed error messages

## Usage

### Method 1: Wrapper Script (Recommended)

Use the bash wrapper script that handles Docker container execution:

```bash
# Dry run - shows what would be deleted (safe)
./scripts/reset_user.sh john.doe

# Actually perform the reset
./scripts/reset_user.sh john.doe --confirm

# Reset but keep media files (only reset database tracking)
./scripts/reset_user.sh john.doe --confirm --keep-media-files

# Show help
./scripts/reset_user.sh --help
```

### Method 2: Direct Python Script

Run the Python script directly inside the Docker container:

```bash
# Enter the container
docker-compose -f docker-compose.latest.yml exec anki-sync-server-nginx bash

# Run the script
python3 /app/scripts/reset_user_collection.py john.doe --confirm
```

## Script Options

| Option | Description |
|--------|-------------|
| `--confirm` | Actually perform the reset (required for safety) |
| `--keep-media-files` | Keep physical media files, only reset database tracking |
| `--data-root` | Root directory for user data (default: `/data`) |

## What Gets Reset

### Complete Reset (default)
- ✅ Collection database (`collection.anki2`)
- ✅ Collection WAL and SHM files
- ✅ All media files in `collection.media/` folder
- ✅ Media database (`collection.media.server.db`)
- ✅ Media database WAL and SHM files
- ✅ Temporary and backup files
- ✅ Recreates empty media folder structure

### With `--keep-media-files`
- ✅ Collection database (`collection.anki2`)
- ✅ Collection WAL and SHM files
- ❌ Media files (kept intact)
- ✅ Media database (`collection.media.server.db`) - forces rebuild
- ✅ Media database WAL and SHM files
- ✅ Temporary and backup files

## Example Output

### Dry Run Analysis
```
=== User Data Analysis: john.doe ===
Total files: 145
Total size: 23.4 MB
Collection: 1,234 cards, 567 notes, USN 42
  Size: 12.1 MB
Media files: 89 files, 11.2 MB
Media database: 89 entries, USN 15
  Tracked: 89 files, 11.2 MB

=== DRY RUN MODE ===
This is a dry run - no changes will be made.
Use --confirm to actually perform the reset.

=== DRY RUN RESULTS ===
Operations that would be performed:
  ✓ Removed collection file: collection.anki2
  ✓ Removed collection file: collection.anki2-wal
  ✓ Removed media folder with 89 files
  ✓ Removed media database: collection.media.server.db
  ✓ Recreated empty media folder

To actually perform this reset, run:
python reset_user_collection.py john.doe --confirm
```

### Actual Reset
```
=== DESTRUCTIVE OPERATION ===
This will permanently delete the user's data!
Are you sure you want to reset user 'john.doe'? (type 'yes' to confirm): yes

=== PERFORMING RESET ===
Operations performed:
  ✓ Removed collection file: collection.anki2
  ✓ Removed collection file: collection.anki2-wal
  ✓ Removed media folder with 89 files
  ✓ Removed media database: collection.media.server.db
  ✓ Recreated empty media folder

✅ Successfully reset user 'john.doe'!
The user can now perform a clean sync from their Anki client.
```

## Safety Considerations

⚠️ **WARNING: This operation is DESTRUCTIVE and cannot be undone!**

- Always run a dry run first to see what will be deleted
- Make sure you have backups before using `--confirm`
- The user will lose all their collection data and sync history
- After reset, the user must perform a full upload from their Anki client

## Post-Reset Process

After running the reset script:

1. **User syncs from Anki client**: The user should sync from their Anki desktop/mobile app
2. **Full upload occurs**: Anki will detect the server has no data and upload the full collection
3. **Clean sync state**: Future syncs will work normally with clean state
4. **Media files rebuild**: Media sync will rebuild the media database as needed

## Troubleshooting

### User Not Found
```
ERROR - User 'username' does not exist in /data/collections
```
**Solution**: Check the username spelling and ensure the user has synced at least once.

### Permission Errors
```
Failed to remove /data/collections/username/collection.anki2: Permission denied
```
**Solution**: Ensure the script is running with appropriate permissions inside the Docker container.

### Database Locked
```
Failed to remove collection.anki2: database is locked
```
**Solution**: Make sure no sync operations are currently running for this user.

## Related Scripts

- `reset_user.sh`: Bash wrapper for easy execution
- `reset_user_collection.py`: Main Python reset script

## Development

To add new functionality or modify the reset behavior:

1. Edit `reset_user_collection.py` for core functionality
2. Update `reset_user.sh` for wrapper script changes
3. Test with dry runs first
4. Update this README with any new options or behaviors