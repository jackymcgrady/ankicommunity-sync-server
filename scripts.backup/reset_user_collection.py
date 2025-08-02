#!/usr/bin/env python3
"""
Reset User Collection Script

This script completely resets a user's collection and media data on the Anki sync server,
providing a clean slate for sync operations. This is useful for:
- Testing sync functionality
- Resolving persistent sync conflicts
- Starting fresh after data corruption
- Development and debugging

Usage:
    python reset_user_collection.py <username> [--confirm] [--keep-media-files]

Options:
    --confirm           Actually perform the reset (required for safety)
    --keep-media-files  Keep physical media files, only reset database tracking
    --dry-run          Show what would be deleted without actually doing it (default)

WARNING: This operation is DESTRUCTIVE and cannot be undone!
"""

import argparse
import logging
import os
import shutil
import sqlite3
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class UserCollectionResetter:
    """Handles complete reset of user collection and media data."""
    
    def __init__(self, data_root="/data"):
        self.data_root = Path(data_root)
        self.collections_root = self.data_root / "collections"
        
    def get_user_path(self, username):
        """Get the path to a user's data directory."""
        return self.collections_root / username
    
    def user_exists(self, username):
        """Check if a user directory exists."""
        user_path = self.get_user_path(username)
        return user_path.exists() and user_path.is_dir()
    
    def get_user_files(self, username):
        """Get a list of all files and directories for a user."""
        user_path = self.get_user_path(username)
        if not user_path.exists():
            return []
        
        files = []
        for item in user_path.rglob("*"):
            if item.is_file():
                files.append(item)
        
        return files
    
    def analyze_user_data(self, username):
        """Analyze user's current data and return summary."""
        user_path = self.get_user_path(username)
        
        if not user_path.exists():
            return {
                "exists": False,
                "collection_file": None,
                "media_folder": None,
                "media_db": None,
                "total_files": 0,
                "total_size": 0
            }
        
        collection_file = user_path / "collection.anki2"
        media_folder = user_path / "collection.media"
        media_db = user_path / "collection.media.server.db"
        
        # Count files and calculate total size
        total_files = 0
        total_size = 0
        
        for item in user_path.rglob("*"):
            if item.is_file():
                total_files += 1
                total_size += item.stat().st_size
        
        # Get collection info
        collection_info = {}
        if collection_file.exists():
            try:
                with sqlite3.connect(str(collection_file)) as conn:
                    cursor = conn.cursor()
                    
                    # Get basic stats
                    cards = cursor.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
                    notes = cursor.execute("SELECT COUNT(*) FROM notes").fetchone()[0] 
                    decks = cursor.execute("SELECT COUNT(*) FROM decks").fetchone()[0]
                    
                    # Get collection mod time
                    col_info = cursor.execute("SELECT crt, mod, scm, usn FROM col").fetchone()
                    
                    collection_info = {
                        "cards": cards,
                        "notes": notes, 
                        "decks": decks,
                        "created": col_info[0] if col_info else 0,
                        "modified": col_info[1] if col_info else 0,
                        "schema": col_info[2] if col_info else 0,
                        "usn": col_info[3] if col_info else 0,
                        "size": collection_file.stat().st_size
                    }
            except Exception as e:
                logger.warning(f"Could not read collection info: {e}")
                collection_info = {"error": str(e)}
        
        # Get media info
        media_info = {}
        if media_folder.exists():
            media_files = [f for f in media_folder.iterdir() if f.is_file()]
            media_size = sum(f.stat().st_size for f in media_files)
            media_info = {
                "files": len(media_files),
                "total_size": media_size
            }
        
        # Get media database info
        media_db_info = {}
        if media_db.exists():
            try:
                with sqlite3.connect(str(media_db)) as conn:
                    cursor = conn.cursor()
                    
                    # Get media database stats
                    media_entries = cursor.execute("SELECT COUNT(*) FROM media").fetchone()[0]
                    meta_info = cursor.execute("SELECT last_usn, total_bytes, total_nonempty_files FROM meta").fetchone()
                    
                    media_db_info = {
                        "entries": media_entries,
                        "last_usn": meta_info[0] if meta_info else 0,
                        "total_bytes": meta_info[1] if meta_info else 0,
                        "total_files": meta_info[2] if meta_info else 0,
                        "size": media_db.stat().st_size
                    }
            except Exception as e:
                logger.warning(f"Could not read media database info: {e}")
                media_db_info = {"error": str(e)}
        
        return {
            "exists": True,
            "collection_file": collection_file if collection_file.exists() else None,
            "media_folder": media_folder if media_folder.exists() else None,
            "media_db": media_db if media_db.exists() else None,
            "total_files": total_files,
            "total_size": total_size,
            "collection_info": collection_info,
            "media_info": media_info,
            "media_db_info": media_db_info
        }
    
    def reset_user_collection(self, username, keep_media_files=False, dry_run=True):
        """
        Completely reset a user's collection and media data.
        
        Args:
            username: The username to reset
            keep_media_files: If True, keep physical media files but reset tracking
            dry_run: If True, only show what would be deleted
        
        Returns:
            dict: Summary of operations performed
        """
        user_path = self.get_user_path(username)
        
        if not user_path.exists():
            logger.error(f"User '{username}' does not exist")
            return {"error": f"User '{username}' does not exist"}
        
        logger.info(f"{'DRY RUN: ' if dry_run else ''}Resetting collection for user: {username}")
        
        operations = []
        errors = []
        
        # Files to handle
        collection_file = user_path / "collection.anki2"
        collection_wal = user_path / "collection.anki2-wal"
        collection_shm = user_path / "collection.anki2-shm"
        media_folder = user_path / "collection.media"
        media_db = user_path / "collection.media.server.db"
        media_db_wal = user_path / "collection.media.server.db-wal"
        media_db_shm = user_path / "collection.media.server.db-shm"
        
        # 1. Remove collection database files
        for db_file in [collection_file, collection_wal, collection_shm]:
            if db_file.exists():
                try:
                    if not dry_run:
                        db_file.unlink()
                    operations.append(f"Removed collection file: {db_file.name}")
                    logger.info(f"{'Would remove' if dry_run else 'Removed'}: {db_file}")
                except Exception as e:
                    error_msg = f"Failed to remove {db_file}: {e}"
                    errors.append(error_msg)
                    logger.error(error_msg)
        
        # 2. Handle media files
        if media_folder.exists():
            if keep_media_files:
                # Keep files but reset tracking by removing media database
                operations.append(f"Kept {len(list(media_folder.iterdir()))} media files")
                logger.info(f"{'Would keep' if dry_run else 'Keeping'} media files in: {media_folder}")
            else:
                # Remove all media files
                try:
                    media_file_count = len([f for f in media_folder.iterdir() if f.is_file()])
                    if not dry_run:
                        shutil.rmtree(media_folder)
                    operations.append(f"Removed media folder with {media_file_count} files")
                    logger.info(f"{'Would remove' if dry_run else 'Removed'}: {media_folder}")
                except Exception as e:
                    error_msg = f"Failed to remove media folder: {e}"
                    errors.append(error_msg)
                    logger.error(error_msg)
        
        # 3. Remove media database files
        for db_file in [media_db, media_db_wal, media_db_shm]:
            if db_file.exists():
                try:
                    if not dry_run:
                        db_file.unlink()
                    operations.append(f"Removed media database: {db_file.name}")
                    logger.info(f"{'Would remove' if dry_run else 'Removed'}: {db_file}")
                except Exception as e:
                    error_msg = f"Failed to remove {db_file}: {e}"
                    errors.append(error_msg)
                    logger.error(error_msg)
        
        # 4. Remove any other temporary or backup files
        temp_patterns = ["*.tmp", "*.bak", "*.backup", "*~"]
        for pattern in temp_patterns:
            for temp_file in user_path.glob(pattern):
                try:
                    if not dry_run:
                        temp_file.unlink()
                    operations.append(f"Removed temporary file: {temp_file.name}")
                    logger.info(f"{'Would remove' if dry_run else 'Removed'}: {temp_file}")
                except Exception as e:
                    error_msg = f"Failed to remove {temp_file}: {e}"
                    errors.append(error_msg)
                    logger.error(error_msg)
        
        # 5. Recreate media folder if we removed it but want to keep the structure
        if not keep_media_files and not dry_run:
            try:
                media_folder.mkdir(exist_ok=True)
                operations.append("Recreated empty media folder")
                logger.info(f"Recreated empty media folder: {media_folder}")
            except Exception as e:
                error_msg = f"Failed to recreate media folder: {e}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        result = {
            "user": username,
            "dry_run": dry_run,
            "operations": operations,
            "errors": errors,
            "success": len(errors) == 0
        }
        
        if dry_run:
            logger.info("DRY RUN completed - no actual changes made")
        else:
            if result["success"]:
                logger.info(f"Successfully reset collection for user: {username}")
            else:
                logger.error(f"Reset completed with {len(errors)} errors")
        
        return result

def format_size(bytes_count):
    """Format bytes as human readable string."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_count < 1024.0:
            return f"{bytes_count:.1f} {unit}"
        bytes_count /= 1024.0
    return f"{bytes_count:.1f} TB"

def main():
    parser = argparse.ArgumentParser(
        description="Reset a user's Anki collection and media data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Dry run (safe) - shows what would be deleted
    python reset_user_collection.py john.doe
    
    # Actually perform the reset
    python reset_user_collection.py john.doe --confirm
    
    # Reset but keep media files
    python reset_user_collection.py john.doe --confirm --keep-media-files
    
WARNING: This operation is DESTRUCTIVE and cannot be undone!
Make sure you have backups before using --confirm.
        """
    )
    
    parser.add_argument("username", help="Username to reset")
    parser.add_argument("--confirm", action="store_true", 
                       help="Actually perform the reset (required for safety)")
    parser.add_argument("--keep-media-files", action="store_true",
                       help="Keep physical media files, only reset database tracking")
    parser.add_argument("--data-root", default="/data",
                       help="Root directory for user data (default: /data)")
    
    args = parser.parse_args()
    
    # Initialize resetter
    resetter = UserCollectionResetter(args.data_root)
    
    # Check if user exists
    if not resetter.user_exists(args.username):
        logger.error(f"User '{args.username}' does not exist in {resetter.collections_root}")
        sys.exit(1)
    
    # Analyze current user data
    logger.info(f"Analyzing data for user: {args.username}")
    analysis = resetter.analyze_user_data(args.username)
    
    print(f"\n=== User Data Analysis: {args.username} ===")
    print(f"Total files: {analysis['total_files']}")
    print(f"Total size: {format_size(analysis['total_size'])}")
    
    if analysis.get("collection_info"):
        info = analysis["collection_info"]
        if "error" in info:
            print(f"Collection: ERROR - {info['error']}")
        else:
            print(f"Collection: {info['cards']} cards, {info['notes']} notes, USN {info['usn']}")
            print(f"  Size: {format_size(info['size'])}")
    
    if analysis.get("media_info"):
        info = analysis["media_info"]
        print(f"Media files: {info['files']} files, {format_size(info['total_size'])}")
    
    if analysis.get("media_db_info"):
        info = analysis["media_db_info"]
        if "error" in info:
            print(f"Media database: ERROR - {info['error']}")
        else:
            print(f"Media database: {info['entries']} entries, USN {info['last_usn']}")
            print(f"  Tracked: {info['total_files']} files, {format_size(info['total_bytes'])}")
    
    # Determine if this is a dry run
    dry_run = not args.confirm
    
    if dry_run:
        print(f"\n=== DRY RUN MODE ===")
        print("This is a dry run - no changes will be made.")
        print("Use --confirm to actually perform the reset.")
    else:
        print(f"\n=== DESTRUCTIVE OPERATION ===")
        print("This will permanently delete the user's data!")
        
        # Final confirmation
        response = input(f"Are you sure you want to reset user '{args.username}'? (type 'yes' to confirm): ")
        if response.lower() != 'yes':
            print("Operation cancelled.")
            sys.exit(0)
    
    # Perform the reset
    print(f"\n{'=== DRY RUN RESULTS ===' if dry_run else '=== PERFORMING RESET ==='}")
    result = resetter.reset_user_collection(
        args.username, 
        keep_media_files=args.keep_media_files,
        dry_run=dry_run
    )
    
    # Display results
    print(f"\nOperations {'that would be' if dry_run else ''} performed:")
    for op in result["operations"]:
        print(f"  ✓ {op}")
    
    if result["errors"]:
        print(f"\nErrors encountered:")
        for error in result["errors"]:
            print(f"  ✗ {error}")
    
    if dry_run:
        print(f"\nTo actually perform this reset, run:")
        print(f"python {sys.argv[0]} {args.username} --confirm")
    else:
        if result["success"]:
            print(f"\n✅ Successfully reset user '{args.username}'!")
            print("The user can now perform a clean sync from their Anki client.")
        else:
            print(f"\n❌ Reset completed with errors. Check the logs above.")
            sys.exit(1)

if __name__ == "__main__":
    main()