#!/usr/bin/env python3
"""
Simple script to purge maxwell3 user data
"""

import psycopg2
import shutil
from pathlib import Path

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'port': '5432',
    'database': 'ankipi',
    'user': 'ankipi',
    'password': 'Huyuping254202'
}

# File system paths
EFS_COLLECTIONS_PATH = Path('/home/ec2-user/ankicommunity-sync-server/efs/collections')

def get_connection():
    """Get database connection"""
    return psycopg2.connect(**DB_CONFIG)

def delete_user_data(conn, profile_id):
    """Delete all user data in correct dependency order"""
    cursor = conn.cursor()

    print("\n📊 Database deletion:")

    # 1. Delete deck_stats
    cursor.execute("DELETE FROM deck_stats WHERE profile_id = %s", (profile_id,))
    print(f"  - Deleted {cursor.rowcount} deck_stats records")

    # 2. Delete deck_recipe_prompts
    cursor.execute("""
        DELETE FROM deck_recipe_prompts
        WHERE deck_id IN (SELECT deck_id FROM decks WHERE profile_id = %s)
    """, (profile_id,))
    print(f"  - Deleted {cursor.rowcount} deck_recipe_prompts records")

    # 3. Delete leech_helper_history
    cursor.execute("""
        DELETE FROM leech_helper_history
        WHERE card_id IN (
            SELECT c.card_id FROM cards c
            JOIN decks d ON c.deck_id = d.deck_id
            WHERE d.profile_id = %s
        )
    """, (profile_id,))
    print(f"  - Deleted {cursor.rowcount} leech_helper_history records")

    # 4. Delete pass records
    cursor.execute("DELETE FROM pass WHERE profile_id = %s", (profile_id,))
    print(f"  - Deleted {cursor.rowcount} pass records")

    # 5. Delete cards
    cursor.execute("""
        DELETE FROM cards
        WHERE deck_id IN (SELECT deck_id FROM decks WHERE profile_id = %s)
    """, (profile_id,))
    print(f"  - Deleted {cursor.rowcount} cards records")

    # 6. Delete card_templates
    cursor.execute("""
        DELETE FROM card_templates
        WHERE note_type_id IN (
            SELECT note_type_id FROM note_types WHERE profile_id = %s
        )
    """, (profile_id,))
    print(f"  - Deleted {cursor.rowcount} card_templates records")

    # 7. Delete note_types
    cursor.execute("DELETE FROM note_types WHERE profile_id = %s", (profile_id,))
    print(f"  - Deleted {cursor.rowcount} note_types records")

    # 8. Delete decks
    cursor.execute("DELETE FROM decks WHERE profile_id = %s", (profile_id,))
    print(f"  - Deleted {cursor.rowcount} decks records")

    # 9. Finally, delete the profile itself
    cursor.execute("DELETE FROM profiles WHERE profile_id = %s", (profile_id,))
    print(f"  - Deleted {cursor.rowcount} profiles record")

    cursor.close()

def delete_user_files(uuid):
    """Delete user's collection directory"""
    collection_path = EFS_COLLECTIONS_PATH / uuid

    if not collection_path.exists():
        print(f"  - No collection directory found: {collection_path}")
        return False

    try:
        shutil.rmtree(collection_path)
        print(f"  - Deleted collection directory: {collection_path}")
        return True
    except Exception as e:
        print(f"  - Error deleting directory: {e}")
        return False

def main():
    print("\n🔍 Purging maxwell3 user data")
    print("=" * 80)

    conn = get_connection()

    try:
        # Find maxwell3 user
        cursor = conn.cursor()
        cursor.execute("SELECT profile_id, uuid FROM profiles WHERE name = 'maxwell3'")
        result = cursor.fetchone()

        if not result:
            print("❌ User maxwell3 not found")
            return

        profile_id, uuid = result
        print(f"✅ Found user: maxwell3 (profile_id: {profile_id}, uuid: {uuid})")

        # Delete database data
        delete_user_data(conn, profile_id)

        # Commit database changes
        conn.commit()
        print("\n✅ Database changes committed")

        # Delete files
        print("\n📁 File system deletion:")
        delete_user_files(uuid)

        print("\n" + "=" * 80)
        print("✅ User maxwell3 has been completely purged")
        print("=" * 80)

    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    main()