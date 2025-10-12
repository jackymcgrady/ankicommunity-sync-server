# User Data Purge Script

Complete user data removal tool for AnkiPi system with GDPR compliance.

## Overview

`purge_user.py` is a comprehensive script that safely deletes all user data from the AnkiPi system, including:

- PostgreSQL database records (all tables with proper FK handling)
- User collection files and backups on EFS
- AWS Cognito authentication records
- Session data
- Audit logging

## Features

- ✅ **Schema-aware**: Automatically validates against current database schema
- ✅ **Safe deletion order**: Respects foreign key constraints (child → parent)
- ✅ **Dry-run mode**: Preview deletions without making changes
- ✅ **Transactional**: All DB operations in atomic transactions
- ✅ **Comprehensive reporting**: Detailed reports with counts and sizes
- ✅ **Audit logging**: JSON logs of all deletion operations
- ✅ **Multiple identifiers**: Find users by UUID, username, or profile ID
- ✅ **Error handling**: Automatic rollback on failures

## Requirements

```bash
pip3 install psycopg2-binary boto3
```

## Usage

### Quick Start

1. **Always start with dry-run:**
   ```bash
   python3 purge_user.py --username maxwell2 --dry-run
   ```

2. **Review the output, then execute:**
   ```bash
   python3 purge_user.py --username maxwell2
   ```

3. **Type 'DELETE' when prompted to confirm**

### Command Options

**By UUID:**
```bash
python3 purge_user.py --uuid a95a654c-8041-7013-bb46-7743060e211c
```

**By Username:**
```bash
python3 purge_user.py --username maxwell2
```

**By Profile ID:**
```bash
python3 purge_user.py --profile-id 18
```

**Dry-run mode (recommended first step):**
```bash
python3 purge_user.py --uuid <uuid> --dry-run
```

**Skip confirmation prompt (dangerous!):**
```bash
python3 purge_user.py --uuid <uuid> --no-confirm
```

**Validate schema:**
```bash
python3 purge_user.py --validate-schema
```

### Help

```bash
python3 purge_user.py --help
```

## Configuration

The script uses environment variables with sensible defaults:

### Database
- `PGHOST` (default: localhost)
- `PGPORT` (default: 5432)
- `PGDATABASE` (default: ankipi)
- `PGUSER` (default: ankipi)
- `PGPASSWORD` (default: Huyuping254202)

### AWS Cognito
- `COGNITO_USER_POOL_ID` (default: ap-southeast-1_aDQ1S4x28)
- `AWS_REGION` (default: ap-southeast-1)

### File Paths
- Collections: `/home/ec2-user/ankicommunity-sync-server/efs/collections`
- Session DB: `/home/ec2-user/ankicommunity-sync-server/efs/session.db`

## Example Output

```
================================================================================
  USER DATA PURGE DELETION REPORT
================================================================================

📋 User Details:
   Username:   maxwell2
   Profile ID: 18
   UUID:       a95a654c-8041-7013-bb46-7743060e211c
   Created:    2025-10-11 15:20:59.621354+00:00
   Active:     True

📊 Database Records DELETED:
   deck_stats                          4 records
   pass                               10 records
   card_templates                     15 records
   note_types                         13 records
   decks                               4 records
   profiles                            1 records
   ----------------------------------------
   TOTAL                              47 records

📁 File System DELETED:
   Path: /home/ec2-user/ankicommunity-sync-server/efs/collections/a95a654c-8041-7013-bb46-7743060e211c
   Files: 4
   Total Size: 224.5 KB

   Files in directory:
     - collection.anki2                                           147.0 KB
     - collection.media.db2                                        24.0 KB
     - AnkiPi_Welcome_Tutorial.apkg                                53.5 KB

🔐 AWS Cognito DELETED:
   ✅ User deleted from Cognito
   Username: maxwell2
   User Pool: ap-southeast-1_aDQ1S4x28

================================================================================
  ✅ User 'maxwell2' has been completely purged
  Total: 47 database records, 4 files
================================================================================

📝 Audit log saved to: /tmp/purge_user_a95a654c-8041-7013-bb46-7743060e211c_20251012_074707.json
```

## Database Schema

The script handles these tables in dependency order (as of Oct 2025):

### Deletion Order (Child → Parent)

1. **leech_helper_history** - Leech card helper history
2. **deck_recipe_prompts** - Recipe prompt associations
3. **deck_stats** - Daily statistics and performance metrics
4. **pass** - Study session passes
5. **cards** - Flashcard records
6. **card_templates** - Card display templates
7. **note_types** - Note type definitions
8. **decks** - User deck collections
9. **profiles** - Main user profile record (last)

### Additional Tables Monitored

- recipe_prompts
- recipes
- recipe_assignments
- old_problems
- check_in
- seeding_rate_limits

## Schema Validation

**Always validate schema after database changes:**

```bash
python3 purge_user.py --validate-schema
```

This will:
- Check all expected tables exist
- Report any new tables not in the script
- Display foreign key relationships
- Alert if script needs updating

## Updating the Script

When the database schema changes:

1. **Run validation:**
   ```bash
   python3 purge_user.py --validate-schema
   ```

2. **If new tables found**, update `DELETION_ORDER` in the script:

   ```python
   DELETION_ORDER = [
       {
           'table': 'new_table',
           'description': 'Description of table',
           'profile_fk': 'profile_id',  # or None
           'join_clause': None  # or complex JOIN
       },
       # ... rest of tables
   ]
   ```

3. **Guidelines:**
   - Add child tables before parent tables
   - Use `profile_fk` if table has direct FK to profiles
   - Use `join_clause` for complex relationships
   - Follow deletion order: leaf nodes → root

4. **Test with dry-run:**
   ```bash
   python3 purge_user.py --uuid <test-uuid> --dry-run
   ```

## Safety Features

### Dry-Run Mode
- Previews all operations without making changes
- Shows exact counts and file lists
- Transaction is rolled back
- Always use this first!

### Transaction Safety
- All DB operations in single transaction
- Automatic rollback on any error
- No partial deletions
- Maintains referential integrity

### Confirmation Prompt
- Requires typing 'DELETE' to proceed
- Shows user details and deletion scope
- Can be skipped with `--no-confirm` (use carefully!)

### Error Handling
- Detailed error messages
- Stack traces for debugging
- Handles missing users gracefully
- Reports AWS credential issues

## Audit Logging

Every deletion creates a JSON audit log:

**Location:** `/tmp/purge_user_<uuid>_<timestamp>.json`

**Contents:**
```json
{
  "timestamp": "2025-10-12T07:47:07.123456+00:00",
  "action": "user_purge",
  "user_info": {
    "profile_id": 18,
    "username": "maxwell2",
    "uuid": "a95a654c-8041-7013-bb46-7743060e211c",
    "created_at": "2025-10-11T15:20:59.621354+00:00",
    "is_active": true
  },
  "deleted_counts": {
    "deck_stats": 4,
    "pass": 10,
    "card_templates": 15,
    "note_types": 13,
    "decks": 4,
    "profiles": 1
  },
  "total_records": 47,
  "total_files": 4,
  "cognito_deleted": true
}
```

## Troubleshooting

### User not found
```
❌ Error: User not found
   UUID: a95a654c-8041-7013-bb46-7743060e211c
```
**Solution:** Verify the identifier is correct. User may already be deleted.

### Database connection error
```
❌ Error: could not connect to server
```
**Solution:** Check database is running and credentials are correct.

### AWS credential error
```
⚠️ Unexpected error: Unable to locate credentials
```
**Solution:** Set AWS credentials or run `aws configure`. Cognito deletion will be skipped but DB/files will still be deleted.

### Foreign key constraint error
```
❌ Error: update or delete on table "profiles" violates foreign key constraint
```
**Solution:** Schema has changed. Run `--validate-schema` and update the script.

### Schema validation warnings
```
⚠️ WARNING: New tables found in database (not in purge script):
    - new_user_table
```
**Solution:** Update `DELETION_ORDER` to include the new table(s).

## GDPR Compliance

This script satisfies GDPR Article 17 ("Right to Erasure"):

- ✅ Removes all personal data from databases
- ✅ Deletes all file system data
- ✅ Removes authentication credentials
- ✅ Maintains audit trail
- ✅ Ensures complete removal (no recovery possible)
- ✅ Respects data integrity during deletion

## Integration with Claude Agent

The user-data-purge agent automatically uses this script. The agent:

1. Validates the schema if README indicates changes
2. Runs dry-run first
3. Presents results for user confirmation
4. Executes actual deletion
5. Reports comprehensive results

See `.claude/agents/user-data-purge.md` for agent instructions.

## Best Practices

1. **Always dry-run first** - Preview before deleting
2. **Validate schema regularly** - After database migrations
3. **Review audit logs** - Keep for compliance records
4. **Test with test users** - Before production use
5. **Backup before deletion** - For critical users (optional)
6. **Update script promptly** - When schema changes

## Script Location

**Primary:** `/home/ec2-user/ankicommunity-sync-server/purge_user.py`

Make executable:
```bash
chmod +x /home/ec2-user/ankicommunity-sync-server/purge_user.py
```

## Support

For issues or questions:
- Check `--help` output
- Review this README
- Validate schema with `--validate-schema`
- Test with `--dry-run` first

## Version History

- **Oct 2025**: Initial version with full schema coverage
  - 9 tables in deletion order
  - AWS Cognito integration
  - Schema validation
  - Comprehensive reporting
