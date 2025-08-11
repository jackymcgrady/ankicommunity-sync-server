#!/usr/bin/env python3
"""
Reset media database for a user to resolve USN mismatch issues.
Use this when client logout/login causes media USN to reset but server retains high USN.
"""

import os
import sys
import sqlite3
import hashlib
import logging
from pathlib import Path

def reset_user_media(username, data_root=None):
    """Reset media database for the specified user."""
    if data_root is None:
        # For host-side scripts, collections are in ./efs/collections
        data_root = os.environ.get('ANKISYNCD_HOST_DATA_ROOT', './efs')
    
    user_folder = Path(data_root) / "collections" / username
    media_folder = user_folder / "collection.media"
    db_path = user_folder / "collection.media.server.db"
    
    if not user_folder.exists():
        print(f"❌ User folder not found: {user_folder}")
        return False
    
    if not media_folder.exists():
        print(f"❌ Media folder not found: {media_folder}")
        return False
    
    print(f"🔄 Resetting media database for user: {username}")
    print(f"   User folder: {user_folder}")
    print(f"   Media folder: {media_folder}")
    print(f"   Database: {db_path}")
    
    try:
        # Connect to media database
        db = sqlite3.connect(str(db_path))
        db.execute("PRAGMA journal_mode=WAL")
        
        print("🗑️  Clearing operation log and resetting USN...")
        
        # Clear the operation log - this removes all USN history
        db.execute("DELETE FROM media_operations")
        
        # Reset meta table to clean state
        db.execute("UPDATE meta SET last_usn = 0, total_bytes = 0, total_nonempty_files = 0")
        
        # Clear current media state table
        db.execute("DELETE FROM media_current")
        
        print("📁 Rebuilding media database from files on disk...")
        
        # Rebuild media_current from actual files on disk
        total_bytes = 0
        total_files = 0
        
        for media_file in media_folder.iterdir():
            if media_file.is_file() and not media_file.name.startswith('.'):
                try:
                    # Read file and calculate checksum
                    with open(media_file, 'rb') as f:
                        data = f.read()
                    
                    if len(data) > 0:  # Only count non-empty files
                        sha1_hash = hashlib.sha1(data).hexdigest()
                        csum_bytes = bytes.fromhex(sha1_hash)
                        file_size = len(data)
                        mtime = int(media_file.stat().st_mtime)
                        
                        # Insert into media_current with USN 0 (fresh state)
                        db.execute("""
                            INSERT OR REPLACE INTO media_current (fname, csum, size, added_usn, mtime)
                            VALUES (?, ?, ?, 0, ?)
                        """, (media_file.name, csum_bytes, file_size, mtime))
                        
                        total_bytes += file_size
                        total_files += 1
                        
                        if total_files <= 5:  # Show first few files
                            print(f"   ✓ {media_file.name} ({file_size} bytes)")
                        elif total_files == 6:
                            print("   ...")
                        
                except Exception as e:
                    print(f"   ⚠️  Could not process file {media_file.name}: {e}")
        
        # Update meta with actual counts
        db.execute("UPDATE meta SET total_bytes = ?, total_nonempty_files = ?", 
                 (total_bytes, total_files))
        
        # Commit all changes
        db.commit()
        db.close()
        
        print(f"✅ Media reset completed:")
        print(f"   📊 Files: {total_files}")
        print(f"   💾 Total size: {total_bytes:,} bytes")
        print(f"   🔄 Server USN reset to: 0")
        print()
        print("🚀 Next sync should not download unnecessary media files!")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to reset media database: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 reset_user_media.py <username>")
        print("Example: python3 reset_user_media.py j.s.bach")
        sys.exit(1)
    
    username = sys.argv[1]
    success = reset_user_media(username)
    sys.exit(0 if success else 1)