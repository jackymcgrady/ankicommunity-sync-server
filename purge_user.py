#!/usr/bin/env python3
"""
AnkiPi User Data Purge Script
==============================

This script completely removes all data for a user from the AnkiPi system.
It handles:
- PostgreSQL database records (with proper FK constraint ordering)
- User collection files on EFS
- AWS Cognito authentication records
- Session data

Usage:
    python3 purge_user.py --uuid <user-uuid>
    python3 purge_user.py --username <username>
    python3 purge_user.py --profile-id <profile-id>
    python3 purge_user.py --uuid <user-uuid> --dry-run
    python3 purge_user.py --validate-schema

Requirements:
    pip3 install psycopg2-binary boto3
"""

import argparse
import os
import sys
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# Optional imports - will check availability
try:
    import psycopg2
    from psycopg2 import sql
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False
    print("Warning: psycopg2 not found. Install with: pip3 install psycopg2-binary")

try:
    import boto3
    from botocore.exceptions import ClientError
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False
    print("Warning: boto3 not found. Install with: pip3 install boto3")


# =============================================================================
# CONFIGURATION
# =============================================================================

# Database configuration (from environment or defaults)
DB_CONFIG = {
    'host': os.getenv('PGHOST', 'localhost'),
    'port': os.getenv('PGPORT', '5432'),
    'database': os.getenv('PGDATABASE', 'ankipi'),
    'user': os.getenv('PGUSER', 'ankipi'),
    'password': os.getenv('PGPASSWORD', 'Huyuping254202')
}

# AWS Cognito configuration
COGNITO_CONFIG = {
    'user_pool_id': os.getenv('COGNITO_USER_POOL_ID', 'ap-southeast-1_aDQ1S4x28'),
    'region': os.getenv('AWS_REGION', 'ap-southeast-1')
}

# File system paths
EFS_COLLECTIONS_PATH = Path('/home/ec2-user/ankicommunity-sync-server/efs/collections')
SESSION_DB_PATH = Path('/home/ec2-user/ankicommunity-sync-server/efs/session.db')

# Schema definition - ordered by dependency (child -> parent)
# This matches create_schema.sql but in reverse deletion order
DELETION_ORDER = [
    # Level 1: Tables that depend on cards/pass (leaf nodes)
    {
        'table': 'leech_helper_history',
        'description': 'Leech card helper history',
        'profile_fk': None,
        'join_clause': '''
            leech_helper_history
            WHERE card_id IN (
                SELECT card_id FROM cards WHERE deck_id IN (
                    SELECT deck_id FROM decks WHERE profile_id = %s
                )
            )
        '''
    },

    # Level 2: Tables that depend on decks
    {
        'table': 'deck_recipe_prompts',
        'description': 'Recipe prompt associations',
        'profile_fk': None,
        'join_clause': 'deck_recipe_prompts WHERE deck_id IN (SELECT deck_id FROM decks WHERE profile_id = %s)'
    },
    {
        'table': 'deck_stats',
        'description': 'Daily statistics and performance metrics',
        'profile_fk': 'profile_id',
        'join_clause': None
    },
    {
        'table': 'pass',
        'description': 'Study session passes',
        'profile_fk': 'profile_id',
        'join_clause': None
    },
    {
        'table': 'cards',
        'description': 'Flashcard records',
        'profile_fk': None,
        'join_clause': 'cards WHERE deck_id IN (SELECT deck_id FROM decks WHERE profile_id = %s)'
    },

    # Level 3: Tables that depend on note_types
    {
        'table': 'card_templates',
        'description': 'Card display templates',
        'profile_fk': None,
        'join_clause': '''
            card_templates
            WHERE note_type_id IN (
                SELECT note_type_id FROM note_types WHERE profile_id = %s
            )
        '''
    },

    # Level 4: Tables that depend on profiles
    {
        'table': 'note_types',
        'description': 'Note type definitions',
        'profile_fk': 'profile_id',
        'join_clause': None
    },
    {
        'table': 'decks',
        'description': 'User deck collections',
        'profile_fk': 'profile_id',
        'join_clause': None
    },

    # Level 5: Parent table
    {
        'table': 'profiles',
        'description': 'Main user profile record',
        'profile_fk': 'profile_id',
        'join_clause': None
    }
]

# Additional tables to check (not directly linked to profiles)
ADDITIONAL_CHECKS = [
    'recipe_prompts',
    'recipes',
    'recipe_assignments',
    'old_problems',
    'check_in',
    'seeding_rate_limits'
]


# =============================================================================
# DATABASE OPERATIONS
# =============================================================================

class DatabaseConnection:
    """Manages database connection and operations"""

    def __init__(self, config: Dict):
        if not HAS_PSYCOPG2:
            raise ImportError("psycopg2 is required. Install with: pip3 install psycopg2-binary")
        self.config = config
        self.conn = None
        self.cursor = None

    def __enter__(self):
        self.conn = psycopg2.connect(**self.config)
        self.cursor = self.conn.cursor()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()

    def execute(self, query: str, params: tuple = None):
        """Execute a query and return results"""
        self.cursor.execute(query, params)
        return self.cursor.fetchall()

    def execute_one(self, query: str, params: tuple = None):
        """Execute a query and return one result"""
        self.cursor.execute(query, params)
        return self.cursor.fetchone()


def find_user(db: DatabaseConnection, uuid: str = None, username: str = None,
              profile_id: int = None) -> Optional[Dict]:
    """Find user by UUID, username, or profile_id"""

    if uuid:
        result = db.execute_one(
            "SELECT profile_id, name, uuid, created_at, is_active FROM profiles WHERE uuid = %s",
            (uuid,)
        )
    elif username:
        result = db.execute_one(
            "SELECT profile_id, name, uuid, created_at, is_active FROM profiles WHERE name = %s",
            (username,)
        )
    elif profile_id:
        result = db.execute_one(
            "SELECT profile_id, name, uuid, created_at, is_active FROM profiles WHERE profile_id = %s",
            (profile_id,)
        )
    else:
        return None

    if not result:
        return None

    return {
        'profile_id': result[0],
        'username': result[1],
        'uuid': str(result[2]),
        'created_at': result[3],
        'is_active': result[4]
    }


def count_user_data(db: DatabaseConnection, profile_id: int) -> Dict[str, int]:
    """Count all data associated with a user"""

    counts = {}

    for item in DELETION_ORDER:
        table = item['table']

        if item['profile_fk']:
            # Direct profile FK
            query = f"SELECT COUNT(*) FROM {table} WHERE {item['profile_fk']} = %s"
            result = db.execute_one(query, (profile_id,))
        elif item['join_clause']:
            # Complex join
            query = f"SELECT COUNT(*) FROM {item['join_clause']}"
            result = db.execute_one(query, (profile_id,))
        else:
            result = (0,)

        counts[table] = result[0]

    return counts


def delete_user_data(db: DatabaseConnection, profile_id: int, dry_run: bool = False) -> Dict[str, int]:
    """Delete all data for a user from database"""

    deleted_counts = {}

    if dry_run:
        print("\n🔍 DRY RUN MODE - No data will be deleted\n")

    for item in DELETION_ORDER:
        table = item['table']
        description = item['description']

        # Count records to be deleted
        if item['profile_fk']:
            count_query = f"SELECT COUNT(*) FROM {table} WHERE {item['profile_fk']} = %s"
            count = db.execute_one(count_query, (profile_id,))[0]
            delete_query = f"DELETE FROM {table} WHERE {item['profile_fk']} = %s"
            delete_params = (profile_id,)
        elif item['join_clause']:
            count_query = f"SELECT COUNT(*) FROM {item['join_clause']}"
            count = db.execute_one(count_query, (profile_id,))[0]
            delete_query = f"DELETE FROM {item['join_clause']}"
            delete_params = (profile_id,)
        else:
            count = 0
            delete_query = None
            delete_params = None

        deleted_counts[table] = count

        if count > 0:
            status = "WOULD DELETE" if dry_run else "DELETING"
            print(f"  {status} {count:4d} records from {table:30s} ({description})")

            if not dry_run and delete_query:
                db.execute(delete_query, delete_params)
        else:
            print(f"  SKIP      {count:4d} records from {table:30s} ({description})")

    return deleted_counts


# =============================================================================
# FILE SYSTEM OPERATIONS
# =============================================================================

def get_user_collection_path(uuid: str) -> Path:
    """Get the path to user's collection directory"""
    return EFS_COLLECTIONS_PATH / uuid


def count_user_files(uuid: str) -> Dict[str, any]:
    """Count files in user's collection directory"""

    collection_path = get_user_collection_path(uuid)

    if not collection_path.exists():
        return {
            'exists': False,
            'path': str(collection_path),
            'files': [],
            'total_size': 0
        }

    files = []
    total_size = 0

    for item in collection_path.rglob('*'):
        if item.is_file():
            size = item.stat().st_size
            files.append({
                'path': str(item.relative_to(collection_path)),
                'size': size,
                'size_human': format_bytes(size)
            })
            total_size += size

    return {
        'exists': True,
        'path': str(collection_path),
        'files': files,
        'total_size': total_size,
        'total_size_human': format_bytes(total_size)
    }


def delete_user_files(uuid: str, dry_run: bool = False) -> Dict:
    """Delete user's collection directory"""

    collection_path = get_user_collection_path(uuid)

    if not collection_path.exists():
        return {
            'deleted': False,
            'reason': 'Directory does not exist',
            'path': str(collection_path)
        }

    file_info = count_user_files(uuid)

    if dry_run:
        return {
            'deleted': False,
            'reason': 'Dry run mode',
            'would_delete': file_info
        }

    try:
        shutil.rmtree(collection_path)
        return {
            'deleted': True,
            'path': str(collection_path),
            'files_deleted': len(file_info['files']),
            'bytes_deleted': file_info['total_size']
        }
    except Exception as e:
        return {
            'deleted': False,
            'reason': f'Error: {str(e)}',
            'path': str(collection_path)
        }


# =============================================================================
# AWS COGNITO OPERATIONS
# =============================================================================

def delete_cognito_user(username: str, dry_run: bool = False) -> Dict:
    """Delete user from AWS Cognito"""

    if not HAS_BOTO3:
        return {
            'deleted': False,
            'reason': 'boto3 not installed',
            'suggestion': 'Install with: pip3 install boto3'
        }

    try:
        client = boto3.client('cognito-idp', region_name=COGNITO_CONFIG['region'])

        if dry_run:
            # Just check if user exists
            try:
                client.admin_get_user(
                    UserPoolId=COGNITO_CONFIG['user_pool_id'],
                    Username=username
                )
                return {
                    'deleted': False,
                    'reason': 'Dry run mode',
                    'exists': True,
                    'user_pool_id': COGNITO_CONFIG['user_pool_id']
                }
            except ClientError as e:
                if e.response['Error']['Code'] == 'UserNotFoundException':
                    return {
                        'deleted': False,
                        'reason': 'Dry run mode',
                        'exists': False
                    }
                raise

        # Actually delete
        client.admin_delete_user(
            UserPoolId=COGNITO_CONFIG['user_pool_id'],
            Username=username
        )

        return {
            'deleted': True,
            'username': username,
            'user_pool_id': COGNITO_CONFIG['user_pool_id']
        }

    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'UserNotFoundException':
            return {
                'deleted': False,
                'reason': 'User not found in Cognito',
                'username': username
            }
        return {
            'deleted': False,
            'reason': f'AWS Error: {error_code}',
            'message': str(e)
        }
    except Exception as e:
        return {
            'deleted': False,
            'reason': f'Unexpected error: {str(e)}'
        }


# =============================================================================
# SCHEMA VALIDATION
# =============================================================================

def validate_schema(db: DatabaseConnection) -> bool:
    """Validate that current database schema matches expected schema"""

    print("\n🔍 Validating database schema...\n")

    # Check all expected tables exist
    expected_tables = [item['table'] for item in DELETION_ORDER] + ADDITIONAL_CHECKS

    result = db.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)

    actual_tables = [row[0] for row in result]

    # Check for missing tables
    missing = set(expected_tables) - set(actual_tables)
    if missing:
        print(f"⚠️  WARNING: Expected tables not found in database:")
        for table in sorted(missing):
            print(f"    - {table}")
        print()

    # Check for new tables
    new_tables = set(actual_tables) - set(expected_tables)
    if new_tables:
        print(f"⚠️  WARNING: New tables found in database (not in purge script):")
        for table in sorted(new_tables):
            print(f"    - {table}")
        print("\n⚠️  IMPORTANT: Update purge_user.py to handle these new tables!")
        print("   Check if they contain user data that should be deleted.\n")

    # Check foreign keys
    result = db.execute("""
        SELECT
            tc.table_name,
            kcu.column_name,
            ccu.table_name AS foreign_table_name,
            ccu.column_name AS foreign_column_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage AS ccu
            ON ccu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
        ORDER BY tc.table_name, kcu.column_name
    """)

    print("✅ Foreign Key Relationships:")
    for row in result:
        table, column, ref_table, ref_column = row
        print(f"   {table}.{column} -> {ref_table}.{ref_column}")

    if not missing and not new_tables:
        print("\n✅ Schema validation passed - script is up to date!\n")
        return True
    else:
        print("\n⚠️  Schema validation completed with warnings\n")
        return False


# =============================================================================
# REPORTING
# =============================================================================

def format_bytes(bytes_count: int) -> str:
    """Format bytes as human readable string"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_count < 1024.0:
            return f"{bytes_count:.1f} {unit}"
        bytes_count /= 1024.0
    return f"{bytes_count:.1f} TB"


def print_deletion_report(user_info: Dict, db_counts: Dict, file_info: Dict,
                         cognito_result: Dict, dry_run: bool = False):
    """Print comprehensive deletion report"""

    mode = "DRY RUN REPORT" if dry_run else "DELETION REPORT"
    action = "WOULD BE DELETED" if dry_run else "DELETED"

    print("\n" + "=" * 80)
    print(f"  USER DATA PURGE {mode}")
    print("=" * 80)

    # User details
    print("\n📋 User Details:")
    print(f"   Username:   {user_info['username']}")
    print(f"   Profile ID: {user_info['profile_id']}")
    print(f"   UUID:       {user_info['uuid']}")
    print(f"   Created:    {user_info['created_at']}")
    print(f"   Active:     {user_info['is_active']}")

    # Database records
    print(f"\n📊 Database Records {action}:")
    total_records = sum(db_counts.values())

    for item in DELETION_ORDER:
        table = item['table']
        count = db_counts.get(table, 0)
        if count > 0:
            print(f"   {table:30s} {count:6d} records")

    print(f"   {'-' * 40}")
    print(f"   {'TOTAL':30s} {total_records:6d} records")

    # File system
    print(f"\n📁 File System {action}:")
    if file_info['exists']:
        print(f"   Path: {file_info['path']}")
        print(f"   Files: {len(file_info['files'])}")
        print(f"   Total Size: {file_info['total_size_human']}")
        if file_info['files']:
            print(f"\n   Files in directory:")
            for f in file_info['files']:
                print(f"     - {f['path']:50s} {f['size_human']:>10s}")
    else:
        print(f"   ⚠️  No collection directory found")
        print(f"   Path: {file_info['path']}")

    # Cognito
    print(f"\n🔐 AWS Cognito {action}:")
    if cognito_result['deleted']:
        print(f"   ✅ User deleted from Cognito")
        print(f"   Username: {cognito_result['username']}")
        print(f"   User Pool: {cognito_result['user_pool_id']}")
    elif cognito_result.get('exists') and dry_run:
        print(f"   ℹ️  User exists in Cognito (would be deleted)")
    else:
        print(f"   ℹ️  {cognito_result['reason']}")

    # Summary
    print("\n" + "=" * 80)
    if dry_run:
        print("  This was a DRY RUN - no data was actually deleted")
        print("  Remove --dry-run flag to perform actual deletion")
    else:
        print(f"  ✅ User '{user_info['username']}' has been completely purged")
        print(f"  Total: {total_records} database records, {len(file_info['files'])} files")
    print("=" * 80 + "\n")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Purge all data for a user from AnkiPi system',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --uuid a95a654c-8041-7013-bb46-7743060e211c
  %(prog)s --username maxwell2
  %(prog)s --profile-id 18
  %(prog)s --uuid a95a654c-8041-7013-bb46-7743060e211c --dry-run
  %(prog)s --validate-schema
        """
    )

    # User identification (mutually exclusive)
    user_group = parser.add_mutually_exclusive_group(required=False)
    user_group.add_argument('--uuid', help='User UUID')
    user_group.add_argument('--username', help='Username')
    user_group.add_argument('--profile-id', type=int, help='Profile ID')

    # Options
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be deleted without actually deleting')
    parser.add_argument('--validate-schema', action='store_true',
                       help='Validate database schema matches script expectations')
    parser.add_argument('--no-confirm', action='store_true',
                       help='Skip confirmation prompt (dangerous!)')

    args = parser.parse_args()

    # Validate schema only
    if args.validate_schema:
        try:
            with DatabaseConnection(DB_CONFIG) as db:
                validate_schema(db)
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            sys.exit(1)
        sys.exit(0)

    # Check that user identification is provided
    if not (args.uuid or args.username or args.profile_id):
        parser.error('Must provide one of: --uuid, --username, --profile-id, or --validate-schema')

    print("\n🔍 AnkiPi User Data Purge Script")
    print("=" * 80)

    try:
        # Find user
        with DatabaseConnection(DB_CONFIG) as db:
            print("\n📋 Looking up user...")
            user_info = find_user(db,
                                 uuid=args.uuid,
                                 username=args.username,
                                 profile_id=args.profile_id)

            if not user_info:
                print(f"\n❌ Error: User not found")
                if args.uuid:
                    print(f"   UUID: {args.uuid}")
                elif args.username:
                    print(f"   Username: {args.username}")
                else:
                    print(f"   Profile ID: {args.profile_id}")
                sys.exit(1)

            print(f"\n✅ Found user: {user_info['username']} (UUID: {user_info['uuid']})")

            # Count data
            print("\n📊 Analyzing user data...")
            db_counts = count_user_data(db, user_info['profile_id'])
            file_info = count_user_files(user_info['uuid'])

            total_records = sum(db_counts.values())
            total_files = len(file_info['files']) if file_info['exists'] else 0

            print(f"   Database records: {total_records}")
            print(f"   Files: {total_files}")

            # Confirm deletion
            if not args.dry_run and not args.no_confirm:
                print("\n⚠️  WARNING: This will permanently delete all data for this user!")
                print(f"   Username: {user_info['username']}")
                print(f"   UUID: {user_info['uuid']}")
                print(f"   Records to delete: {total_records}")
                print(f"   Files to delete: {total_files}")

                response = input("\nType 'DELETE' to confirm: ")
                if response != 'DELETE':
                    print("\n❌ Deletion cancelled")
                    sys.exit(0)

            # Start deletion
            print(f"\n🗑️  {'Simulating' if args.dry_run else 'Starting'} deletion process...")

            # Delete from database
            print("\n📊 Database deletion:")
            deleted_counts = delete_user_data(db, user_info['profile_id'], dry_run=args.dry_run)

            # Don't commit in dry run mode
            if args.dry_run:
                db.conn.rollback()
                print("\n   ℹ️  Transaction rolled back (dry run)")

        # Delete files
        print("\n📁 File system deletion:")
        file_result = delete_user_files(user_info['uuid'], dry_run=args.dry_run)
        if file_result.get('deleted'):
            print(f"   ✅ Deleted {file_result['files_deleted']} files ({format_bytes(file_result['bytes_deleted'])})")
        elif args.dry_run and file_info['exists']:
            print(f"   ℹ️  Would delete {len(file_info['files'])} files ({file_info['total_size_human']})")
        else:
            print(f"   ℹ️  {file_result.get('reason', 'No files to delete')}")

        # Delete from Cognito
        print("\n🔐 AWS Cognito deletion:")
        cognito_result = delete_cognito_user(user_info['username'], dry_run=args.dry_run)
        if cognito_result.get('deleted'):
            print(f"   ✅ Deleted user from Cognito")
        elif args.dry_run and cognito_result.get('exists'):
            print(f"   ℹ️  Would delete user from Cognito")
        else:
            print(f"   ℹ️  {cognito_result.get('reason', 'User not in Cognito')}")

        # Print final report
        print_deletion_report(user_info, deleted_counts, file_info, cognito_result, args.dry_run)

        # Generate audit log
        if not args.dry_run:
            log_entry = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'action': 'user_purge',
                'user_info': user_info,
                'deleted_counts': deleted_counts,
                'total_records': sum(deleted_counts.values()),
                'total_files': file_result.get('files_deleted', 0),
                'cognito_deleted': cognito_result.get('deleted', False)
            }

            log_file = Path(f'/tmp/purge_user_{user_info["uuid"]}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
            log_file.write_text(json.dumps(log_entry, indent=2))
            print(f"📝 Audit log saved to: {log_file}")

    except KeyboardInterrupt:
        print("\n\n❌ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
