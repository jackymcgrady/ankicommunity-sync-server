# User Initiation for Anki Sync Server

## Overview
When a user signs up on the ankipi webapp, you need to initialize their profile in both the database and file system for the Anki sync server. This should happen immediately upon successful user registration, before they ever attempt to sync with Anki.

## Database Operations

### 1. User Profile Table
Create a user profile record that maps the user's Cognito UUID to their username.

**Database**: The sync server uses a user profile database (likely PostgreSQL or SQLite)
**Table**: `user_profiles` (or similar)
**Required Fields**:
- `uuid` (VARCHAR) - The Cognito user ID (sub field from JWT token)
- `username` (VARCHAR) - The user's chosen username
- `created_at` (TIMESTAMP) - When the profile was created
- `updated_at` (TIMESTAMP) - Last updated timestamp

**SQL Example**:
```sql
INSERT INTO user_profiles (uuid, username, created_at, updated_at)
VALUES (?, ?, NOW(), NOW())
```

### 2. Authentication Database (Optional)
If the sync server maintains a local auth database for fallback/compatibility:
**Database**: `auth.db` (SQLite)
**Table**: `auth`
**Fields**: Add user with placeholder password since Cognito handles authentication

## File System Operations

### 1. Collection Directory Creation
Create the user's collection directory in the server's data storage.

**Base Path**: `./efs/collections/` (from host perspective)
**User Directory**: `./efs/collections/{cognito_uuid}/`

**Operations**:
1. Create directory: `mkdir -p ./efs/collections/{cognito_uuid}`
2. Set appropriate permissions (readable/writable by sync server process)
3. Initialize empty state - no files needed initially

### 2. Directory Structure
The created directory will eventually contain:
- `collection.anki2` - User's Anki database (created on first sync)
- `collection.anki2-wal` - SQLite WAL file
- `collection.media.server.db` - Media sync database
- Media files (images, audio, etc.)

**Note**: Don't pre-create these files - let the sync server create them on first sync.

## Implementation Requirements

### Input Data Needed
From user registration:
- `cognito_user_id` - The UUID from Cognito (JWT sub field)
- `username` - User's chosen username
- `email` - User's email (for logging/tracking)

### Error Handling
- Check if user already exists before creating
- Handle file system permission errors
- Validate cognito_user_id format (should be UUID)
- Rollback database changes if file system operations fail

### Success Response
Return confirmation that:
- Database profile created successfully
- Collection directory created at path: `./efs/collections/{cognito_uuid}`
- User is ready for Anki sync

## Integration Notes

### Timing
- Call this immediately after successful Cognito user confirmation
- Before user receives any "account ready" notifications
- Independent of user's first Anki sync attempt

### Security
- Validate the cognito_user_id is authentic (from your JWT token)
- Don't expose file system paths in API responses
- Log initiation attempts for debugging

### Database Connection
- Use the same database connection/configuration as the sync server
- Consider connection pooling for high-volume signups
- Handle database connection failures gracefully

## Example Flow
1. User completes signup on ankipi webapp
2. Cognito user created and confirmed
3. Your webapp receives Cognito user details
4. Extract `cognito_user_id` from JWT token
5. Call user initiation with `{cognito_user_id, username, email}`
6. Create database profile record
7. Create file system directory `./efs/collections/{cognito_user_id}/`
8. Return success confirmation
9. User account is now ready for Anki sync

## File Paths Reference
- **Host perspective**: `./efs/collections/{uuid}/`
- **Container perspective**: `/data/collections/{uuid}/`
- **Volume mount**: `./efs:/data` in docker-compose

The sync server expects users to be identified by their Cognito UUID in both database and file system paths.