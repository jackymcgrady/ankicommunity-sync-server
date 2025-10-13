#!/usr/bin/env python3
"""
User Data Purge Script for AnkiPi
Permanently deletes all data for user "maxwell2" from the PostgreSQL database
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import shutil

# Database configuration
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', '172.17.0.1'),
    'port': os.getenv('POSTGRES_PORT', '5432'),
    'database': os.getenv('POSTGRES_DB', 'ankipi'),
    'user': os.getenv('POSTGRES_USER', 'ankipi'),
    'password': os.getenv('POSTGRES_PASSWORD', 'Huyuping254202')
}

TARGET_USERNAME = 'maxwell2'

def get_connection():
    """Get a database connection."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except psycopg2.Error as e:
        print(f"ERROR: Database connection failed: {e}")
        sys.exit(1)

def confirm_deletion(auto_confirm=False):
    """Confirm deletion intent with user."""
    print("=" * 80)
    print("WARNING: USER DATA DELETION")
    print("=" * 80)
    print(f"\nThis will permanently delete ALL data for user: {TARGET_USERNAME}")
    print("\nThis includes:")
    print("  - User profile and account information")
    print("  - All decks and cards")
    print("  - All media files")
    print("  - All note types and templates")
    print("  - All statistics and history")
    print("  - All related database records")
    print("\nThis action CANNOT be undone!")
    print("\n" + "=" * 80)

    if auto_confirm:
        print("\nAuto-confirm mode enabled. Proceeding with deletion...")
        return

    response = input("\nType 'DELETE maxwell2' to confirm deletion: ")
    if response != 'DELETE maxwell2':
        print("\nDeletion cancelled.")
        sys.exit(0)

    print("\nProceeding with deletion...")

def find_user(conn):
    """Find the user and return their details."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT profile_id, uuid, name, created_at, is_active, anki2_filename
            FROM profiles
            WHERE name = %s
        """, (TARGET_USERNAME,))

        user = cur.fetchone()
        if user:
            return dict(user)
        return None

def get_deletion_counts(conn, profile_id):
    """Get counts of all records to be deleted."""
    counts = {}

    with conn.cursor() as cur:
        # Deck stats
        cur.execute("SELECT COUNT(*) FROM deck_stats WHERE profile_id = %s", (profile_id,))
        counts['deck_stats'] = cur.fetchone()[0]

        # Deck recipe prompts (through decks)
        cur.execute("""
            SELECT COUNT(*) FROM deck_recipe_prompts drp
            WHERE drp.deck_id IN (SELECT deck_id FROM decks WHERE profile_id = %s)
        """, (profile_id,))
        counts['deck_recipe_prompts'] = cur.fetchone()[0]

        # Leech helper history (through cards -> decks)
        cur.execute("""
            SELECT COUNT(*) FROM leech_helper_history lhh
            WHERE lhh.card_id IN (
                SELECT c.card_id FROM cards c
                JOIN decks d ON c.deck_id = d.deck_id
                WHERE d.profile_id = %s
            )
        """, (profile_id,))
        counts['leech_helper_history'] = cur.fetchone()[0]

        # Pass records
        cur.execute("SELECT COUNT(*) FROM pass WHERE profile_id = %s", (profile_id,))
        counts['pass'] = cur.fetchone()[0]

        # Cards (through decks)
        cur.execute("""
            SELECT COUNT(*) FROM cards c
            JOIN decks d ON c.deck_id = d.deck_id
            WHERE d.profile_id = %s
        """, (profile_id,))
        counts['cards'] = cur.fetchone()[0]

        # Card templates (through note_types)
        cur.execute("""
            SELECT COUNT(*) FROM card_templates ct
            WHERE ct.note_type_id IN (
                SELECT note_type_id FROM note_types WHERE profile_id = %s
            )
        """, (profile_id,))
        counts['card_templates'] = cur.fetchone()[0]

        # Note types
        cur.execute("SELECT COUNT(*) FROM note_types WHERE profile_id = %s", (profile_id,))
        counts['note_types'] = cur.fetchone()[0]

        # Decks
        cur.execute("SELECT COUNT(*) FROM decks WHERE profile_id = %s", (profile_id,))
        counts['decks'] = cur.fetchone()[0]

        # Profile (should be 1)
        counts['profiles'] = 1

    return counts

def delete_user_data(conn, profile_id):
    """Delete all user data in correct dependency order."""
    deletion_log = {}

    with conn.cursor() as cur:
        # 1. Delete deck_stats (depends on deck_id and profile_id)
        cur.execute("DELETE FROM deck_stats WHERE profile_id = %s", (profile_id,))
        deletion_log['deck_stats'] = cur.rowcount
        print(f"  - Deleted {cur.rowcount} deck_stats records")

        # 2. Delete deck_recipe_prompts (depends on deck_id)
        cur.execute("""
            DELETE FROM deck_recipe_prompts
            WHERE deck_id IN (SELECT deck_id FROM decks WHERE profile_id = %s)
        """, (profile_id,))
        deletion_log['deck_recipe_prompts'] = cur.rowcount
        print(f"  - Deleted {cur.rowcount} deck_recipe_prompts records")

        # 3. Delete leech_helper_history (depends on card_id and pass_id)
        cur.execute("""
            DELETE FROM leech_helper_history
            WHERE card_id IN (
                SELECT c.card_id FROM cards c
                JOIN decks d ON c.deck_id = d.deck_id
                WHERE d.profile_id = %s
            )
        """, (profile_id,))
        deletion_log['leech_helper_history'] = cur.rowcount
        print(f"  - Deleted {cur.rowcount} leech_helper_history records")

        # 4. Delete pass records (depends on profile_id and deck_id)
        cur.execute("DELETE FROM pass WHERE profile_id = %s", (profile_id,))
        deletion_log['pass'] = cur.rowcount
        print(f"  - Deleted {cur.rowcount} pass records")

        # 5. Delete cards (depends on deck_id)
        cur.execute("""
            DELETE FROM cards
            WHERE deck_id IN (SELECT deck_id FROM decks WHERE profile_id = %s)
        """, (profile_id,))
        deletion_log['cards'] = cur.rowcount
        print(f"  - Deleted {cur.rowcount} cards records")

        # 6. Delete card_templates (depends on note_type_id)
        cur.execute("""
            DELETE FROM card_templates
            WHERE note_type_id IN (
                SELECT note_type_id FROM note_types WHERE profile_id = %s
            )
        """, (profile_id,))
        deletion_log['card_templates'] = cur.rowcount
        print(f"  - Deleted {cur.rowcount} card_templates records")

        # 7. Delete note_types (depends on profile_id)
        cur.execute("DELETE FROM note_types WHERE profile_id = %s", (profile_id,))
        deletion_log['note_types'] = cur.rowcount
        print(f"  - Deleted {cur.rowcount} note_types records")

        # 8. Delete decks (depends on profile_id)
        cur.execute("DELETE FROM decks WHERE profile_id = %s", (profile_id,))
        deletion_log['decks'] = cur.rowcount
        print(f"  - Deleted {cur.rowcount} decks records")

        # 9. Finally, delete the profile itself
        cur.execute("DELETE FROM profiles WHERE profile_id = %s", (profile_id,))
        deletion_log['profiles'] = cur.rowcount
        print(f"  - Deleted {cur.rowcount} profiles record")

    return deletion_log

def delete_user_files(username):
    """Delete user collection files and media from filesystem."""
    deleted_files = []

    # Check common user data locations
    possible_paths = [
        f"/data/collections/{username}",
        f"./data/collections/{username}",
        f"/home/ec2-user/ankicommunity-sync-server/data/collections/{username}",
        f"/home/ec2-user/ankicommunity-sync-server/efs/collections/{username}",
        f"./efs/collections/{username}"
    ]

    for path in possible_paths:
        if os.path.exists(path):
            try:
                shutil.rmtree(path)
                deleted_files.append(path)
                print(f"  - Deleted directory: {path}")
            except Exception as e:
                print(f"  - WARNING: Failed to delete {path}: {e}")

    return deleted_files

def verify_deletion(conn, profile_id, username):
    """Verify that no records remain for the user."""
    issues = []

    with conn.cursor() as cur:
        # Check profiles
        cur.execute("SELECT COUNT(*) FROM profiles WHERE profile_id = %s", (profile_id,))
        if cur.fetchone()[0] > 0:
            issues.append("profiles table still has records")

        # Check decks
        cur.execute("SELECT COUNT(*) FROM decks WHERE profile_id = %s", (profile_id,))
        if cur.fetchone()[0] > 0:
            issues.append("decks table still has records")

        # Check cards
        cur.execute("""
            SELECT COUNT(*) FROM cards c
            JOIN decks d ON c.deck_id = d.deck_id
            WHERE d.profile_id = %s
        """, (profile_id,))
        if cur.fetchone()[0] > 0:
            issues.append("cards table still has records")

        # Check note_types
        cur.execute("SELECT COUNT(*) FROM note_types WHERE profile_id = %s", (profile_id,))
        if cur.fetchone()[0] > 0:
            issues.append("note_types table still has records")

        # Check pass
        cur.execute("SELECT COUNT(*) FROM pass WHERE profile_id = %s", (profile_id,))
        if cur.fetchone()[0] > 0:
            issues.append("pass table still has records")

        # Check deck_stats
        cur.execute("SELECT COUNT(*) FROM deck_stats WHERE profile_id = %s", (profile_id,))
        if cur.fetchone()[0] > 0:
            issues.append("deck_stats table still has records")

    return issues

def main():
    # Check for auto-confirm flag
    auto_confirm = '--confirm' in sys.argv or '-y' in sys.argv

    print("\n" + "=" * 80)
    print("AnkiPi User Data Purge Script")
    print("=" * 80)
    print(f"\nTarget user: {TARGET_USERNAME}")
    print(f"Database: {DB_CONFIG['database']} at {DB_CONFIG['host']}")
    print(f"Timestamp: {datetime.now().isoformat()}")

    # Step 1: Confirm deletion
    confirm_deletion(auto_confirm)

    # Step 2: Connect to database
    print("\n[1/7] Connecting to database...")
    conn = get_connection()
    print("  Connected successfully")

    try:
        # Step 3: Find user
        print(f"\n[2/7] Finding user '{TARGET_USERNAME}'...")
        user = find_user(conn)

        if not user:
            print(f"  ERROR: User '{TARGET_USERNAME}' not found in database")
            sys.exit(1)

        print(f"  User found:")
        print(f"    - Profile ID: {user['profile_id']}")
        print(f"    - UUID: {user['uuid']}")
        print(f"    - Name: {user['name']}")
        print(f"    - Created: {user['created_at']}")
        print(f"    - Active: {user['is_active']}")

        profile_id = user['profile_id']

        # Step 4: Get deletion counts
        print(f"\n[3/7] Analyzing data to be deleted...")
        counts = get_deletion_counts(conn, profile_id)
        total_records = sum(counts.values())

        print(f"  Records to be deleted:")
        for table, count in counts.items():
            if count > 0:
                print(f"    - {table}: {count}")
        print(f"  Total records: {total_records}")

        # Step 5: Execute deletion in transaction
        print(f"\n[4/7] Executing deletion in transaction...")
        # Transaction is started automatically with psycopg2, just ensure autocommit is off
        # Note: Connection already has autocommit=False by default

        deletion_log = delete_user_data(conn, profile_id)

        # Step 6: Verify deletion
        print(f"\n[5/7] Verifying deletion...")
        issues = verify_deletion(conn, profile_id, TARGET_USERNAME)

        if issues:
            print("  ERROR: Verification failed with issues:")
            for issue in issues:
                print(f"    - {issue}")
            print("\n  Rolling back transaction...")
            conn.rollback()
            sys.exit(1)

        print("  Verification passed - all database records removed")

        # Step 7: Commit transaction
        print(f"\n[6/7] Committing transaction...")
        conn.commit()
        print("  Transaction committed successfully")

        # Step 8: Delete filesystem files
        print(f"\n[7/7] Deleting user files from filesystem...")
        deleted_files = delete_user_files(TARGET_USERNAME)
        if deleted_files:
            print(f"  Deleted {len(deleted_files)} directory(ies)")
        else:
            print("  No user directories found on filesystem")

        # Generate final report
        print("\n" + "=" * 80)
        print("DELETION REPORT")
        print("=" * 80)
        print(f"User Identifier: {TARGET_USERNAME}")
        print(f"Profile ID: {profile_id}")
        print(f"UUID: {user['uuid']}")
        print(f"Timestamp: {datetime.now().isoformat()}")
        print(f"\nDeleted Records:")

        total_deleted = 0
        for table, count in deletion_log.items():
            print(f"  - {table}: {count}")
            total_deleted += count

        print(f"\nTotal records deleted: {total_deleted}")

        if deleted_files:
            print(f"\nDeleted directories:")
            for path in deleted_files:
                print(f"  - {path}")

        print(f"\nStatus: SUCCESS")
        print("=" * 80)
        print("\nUser deletion completed successfully!")
        print("All data for user 'maxwell2' has been permanently removed.\n")

    except Exception as e:
        print(f"\n  ERROR: {e}")
        print("  Rolling back transaction...")
        conn.rollback()
        print("\nDeletion failed. Database has been rolled back to previous state.")
        sys.exit(1)

    finally:
        conn.close()

if __name__ == "__main__":
    main()
