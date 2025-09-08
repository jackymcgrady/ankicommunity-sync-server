# -*- coding: utf-8 -*-
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import os
import io
import json
import zipfile
import hashlib
import logging
import sqlite3
import time
import unicodedata
from typing import List, Dict, Tuple, Optional, Any
from pathlib import Path

import anki.utils
from anki.utils import checksum

logger = logging.getLogger("ankisyncd.media_manager")

# Raised when the client requests a media file that the server's DB says exists,
# but the corresponding file is missing on disk. Used to trigger a 409 response.
class MediaConflict(Exception):
    pass

# Constants from Anki reference code
MAX_MEDIA_FILENAME_LENGTH = 120
MAX_MEDIA_FILENAME_LENGTH_SERVER = 255
MAX_INDIVIDUAL_MEDIA_FILE_SIZE = 100 * 1024 * 1024  # 100MB
MAX_MEDIA_FILES_IN_ZIP = 25
MEDIA_SYNC_TARGET_ZIP_BYTES = int(2.5 * 1024 * 1024)  # 2.5MB


class ServerMediaDatabase:
    """Modern server-side media database compatible with Anki's latest protocol."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.db = None
        self._init_database()
    
    def _init_database(self):
        """Initialize the media database with modern schema."""
        create_new = not os.path.exists(self.db_path)
        self.db = sqlite3.connect(self.db_path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        
        if create_new:
            self._create_schema()
            # Check if we're creating a new database in a folder with existing media files
            # This indicates a collection upload scenario where USN alignment is needed
            self._create_operation_log_for_existing_files()
        else:
            self._upgrade_schema()
    
    def _create_schema(self):
        """Create the correct append-only operation log schema."""
        self.db.executescript("""
            -- Append-only operation log (core of media sync)
            CREATE TABLE media_operations (
                usn INTEGER PRIMARY KEY,
                operation TEXT NOT NULL CHECK (operation IN ('add', 'remove')),
                fname TEXT NOT NULL,
                csum BLOB,      -- NULL for remove operations
                size INTEGER,   -- NULL for remove operations  
                timestamp INTEGER NOT NULL
            );
            
            -- Current media state (derived from operations)
            CREATE TABLE media_current (
                fname TEXT PRIMARY KEY,
                csum BLOB NOT NULL,
                size INTEGER NOT NULL,
                added_usn INTEGER NOT NULL,
                mtime INTEGER NOT NULL
            );
            
            -- Global metadata
            CREATE TABLE meta (
                last_usn INTEGER NOT NULL,
                total_bytes INTEGER NOT NULL,
                total_nonempty_files INTEGER NOT NULL
            );
            
            -- Indexes for efficient queries
            CREATE INDEX ix_operations_usn ON media_operations (usn);
            CREATE INDEX ix_operations_fname ON media_operations (fname);
            CREATE INDEX ix_current_usn ON media_current (added_usn);
            
            INSERT INTO meta (last_usn, total_bytes, total_nonempty_files) 
            VALUES (0, 0, 0);
            
            PRAGMA user_version = 5;
        """)
        self.db.commit()
        logger.info("Created new append-only operation log media database schema")
    
    def _upgrade_schema(self):
        """Upgrade legacy media database to correct operation log schema."""
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        
        if version < 5:
            logger.info(f"Upgrading media database from version {version} to 5 (operation log)")
            
            # Check if we have any existing schema  
            tables = self.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = [t[0] for t in tables]
            
            if 'media' in table_names or 'media_current' in table_names:
                logger.warning("🔄 MIGRATING FROM INCORRECT USN SCHEMA TO OPERATION LOG")
                
                # Backup existing data before migration
                existing_files = []
                try:
                    if 'media' in table_names:
                        # Extract current files from old incorrect schema
                        rows = self.db.execute("SELECT fname, csum, size, mtime FROM media WHERE csum IS NOT NULL").fetchall()
                        existing_files = [(fname, csum, size if size else 0, mtime) for fname, csum, size, mtime in rows]
                        logger.info(f"Found {len(existing_files)} files in old schema to migrate")
                    elif 'media_current' in table_names:
                        # Extract from slightly newer but still incorrect schema
                        rows = self.db.execute("SELECT fname, csum, size, mtime FROM media_current").fetchall()
                        existing_files = [(fname, csum, size, mtime) for fname, csum, size, mtime in rows]
                        logger.info(f"Found {len(existing_files)} files in current table to migrate")
                except Exception as e:
                    logger.warning(f"Could not extract existing files for migration: {e}")
                
                # Drop all old tables and recreate with correct schema
                self.db.executescript("""
                    BEGIN EXCLUSIVE;
                    DROP TABLE IF EXISTS media;
                    DROP TABLE IF EXISTS media_current;
                    DROP TABLE IF EXISTS media_operations;
                    DROP TABLE IF EXISTS meta;
                    DROP INDEX IF EXISTS ix_usn;
                    DROP INDEX IF EXISTS ix_operations_usn;
                    DROP INDEX IF EXISTS ix_operations_fname;
                    DROP INDEX IF EXISTS ix_current_usn;
                    COMMIT;
                """)
                
                # Create new correct schema
                self._create_schema()
                
                # Migrate existing files as ADD operations
                if existing_files:
                    logger.info(f"Creating operation log entries for {len(existing_files)} existing files")
                    current_time = int(time.time())
                    
                    for i, (fname, csum, size, mtime) in enumerate(existing_files, 1):
                        # Normalize filename to NFC for protocol/database consistency
                        try:
                            fname = unicodedata.normalize("NFC", fname)
                        except Exception:
                            pass
                        # Each existing file becomes an ADD operation with sequential USN
                        self.db.execute("""
                            INSERT INTO media_operations (usn, operation, fname, csum, size, timestamp)
                            VALUES (?, 'add', ?, ?, ?, ?)
                        """, (i, fname, csum, size, current_time))
                        
                        # Also add to current state
                        self.db.execute("""
                            INSERT INTO media_current (fname, csum, size, added_usn, mtime)
                            VALUES (?, ?, ?, ?, ?)
                        """, (fname, csum, size, i, mtime))
                    
                    # Update meta with final USN
                    self.db.execute("""
                        UPDATE meta SET 
                            last_usn = ?,
                            total_nonempty_files = ?,
                            total_bytes = ?
                    """, (len(existing_files), len(existing_files), sum(size for _, _, size, _ in existing_files)))
                    
                    self.db.commit()
                    logger.info(f"✅ Migration complete: {len(existing_files)} operations in log, last_usn={len(existing_files)}")
                else:
                    logger.info("✅ Migration complete: No existing files, clean operation log")
            else:
                # No existing tables, create fresh schema
                logger.info("Creating fresh operation log schema")
                self._create_operation_log_for_existing_files()
    
    def _create_operation_log_for_existing_files(self):
        """Create operation log entries for existing media files on disk."""
        try:
            # Get the directory containing the database
            media_folder = Path(self.db_path).parent / "collection.media"
            
            if media_folder.exists():
                # Find existing media files
                existing_files = []
                for file_path in media_folder.iterdir():
                    if file_path.is_file() and not file_path.name.startswith('.'):
                        try:
                            # Calculate file info
                            stat_result = file_path.stat()
                            with open(file_path, 'rb') as f:
                                content = f.read()
                                csum = hashlib.sha1(content).digest()
                            
                            existing_files.append((
                                file_path.name,
                                csum,
                                len(content),
                                int(stat_result.st_mtime)
                            ))
                        except Exception as e:
                            logger.warning(f"Could not process existing file {file_path.name}: {e}")
                
                if existing_files:
                    logger.warning(f"🔄 Creating operation log for {len(existing_files)} existing media files")
                    current_time = int(time.time())
                    
                    for i, (fname, csum, size, mtime) in enumerate(existing_files, 1):
                        # Normalize filename to NFC for protocol/database consistency
                        try:
                            fname = unicodedata.normalize("NFC", fname)
                        except Exception:
                            pass
                        # Each existing file becomes an ADD operation with sequential USN
                        self.db.execute("""
                            INSERT INTO media_operations (usn, operation, fname, csum, size, timestamp)
                            VALUES (?, 'add', ?, ?, ?, ?)
                        """, (i, fname, csum, size, current_time))
                        
                        # Also add to current state
                        self.db.execute("""
                            INSERT INTO media_current (fname, csum, size, added_usn, mtime)
                            VALUES (?, ?, ?, ?, ?)
                        """, (fname, csum, size, i, mtime))
                    
                    # Update meta with final USN
                    self.db.execute("""
                        UPDATE meta SET 
                            last_usn = ?,
                            total_nonempty_files = ?,
                            total_bytes = ?
                    """, (len(existing_files), len(existing_files), sum(size for _, _, size, _ in existing_files)))
                    
                    self.db.commit()
                    logger.info(f"✅ Operation log created: {len(existing_files)} ADD operations, last_usn={len(existing_files)}")
                else:
                    logger.info("✅ No existing media files found, clean operation log ready")
        except Exception as e:
            logger.error(f"Error creating operation log for existing files: {e}")
    
    
    def last_usn(self) -> int:
        """Get the last USN from the database."""
        result = self.db.execute("SELECT last_usn FROM meta").fetchone()
        usn = result[0] if result else 0
        
        # Defensive check: if USN is 0 but files exist in database, fix the USN
        if usn == 0:
            file_count = self.db.execute("SELECT COUNT(*) FROM media_current").fetchone()[0]
            if file_count > 0:
                logger.warning(f"🔧 DEFENSIVE FIX: USN=0 but {file_count} files in database, fixing USN")
                try:
                    # Find the highest USN from media_current table and fix meta table
                    max_usn = self.db.execute("SELECT MAX(added_usn) FROM media_current").fetchone()[0]
                    if max_usn and max_usn > 0:
                        self.db.execute("UPDATE meta SET last_usn = ?", (max_usn,))
                        self.db.commit()
                        usn = max_usn
                        logger.warning(f"🔧 DEFENSIVE FIX: Updated USN to {usn}")
                    else:
                        logger.warning("🔧 DEFENSIVE FIX: No valid USN found in media_current, rebuilding database")
                        # Last resort: rebuild the database
                        db_path = self.db_path
                        self.close()
                        os.rename(db_path, f"{db_path}.backup")
                        self.__init__(db_path)
                        usn = self.db.execute("SELECT last_usn FROM meta").fetchone()[0]
                        logger.warning(f"🔧 DEFENSIVE FIX: USN after rebuild: {usn}")
                except Exception as e:
                    logger.error(f"Defensive USN fix failed: {e}")
        
        return usn
    
    def media_changes_chunk(self, after_usn: int) -> List[Tuple[str, int, str]]:
        """Get media operations after the specified USN from the operation log."""
        operations = self.db.execute("""
            SELECT fname, usn, 
                   CASE WHEN operation = 'remove' THEN '' 
                        ELSE hex(csum) END as csum_hex
            FROM media_operations 
            WHERE usn > ? 
            ORDER BY usn 
            LIMIT 250
        """, (after_usn,)).fetchall()
        
        return [(fname, usn, csum_hex) for fname, usn, csum_hex in operations]
    
    def nonempty_file_count(self) -> int:
        """Get count of non-empty files."""
        result = self.db.execute("SELECT total_nonempty_files FROM meta").fetchone()
        return result[0] if result else 0
    
    def recalculate_file_count(self) -> int:
        """Recalculate and fix the file count in meta table."""
        actual_count = self.db.execute("SELECT COUNT(*) FROM media_current WHERE size > 0").fetchone()[0]
        actual_bytes = self.db.execute("SELECT COALESCE(SUM(size), 0) FROM media_current WHERE size > 0").fetchone()[0]
        
        self.db.execute("""
            UPDATE meta SET 
                total_nonempty_files = ?,
                total_bytes = ?
        """, (actual_count, actual_bytes))
        self.db.commit()
        
        logger.info(f"Recalculated media counts: files={actual_count}, bytes={actual_bytes}")
        return actual_count
    
    def forget_missing_file(self, filename: str) -> None:
        """Record a removal for a file missing on disk to bring operation log/current state
        back into consistency. This prevents clients from repeatedly attempting to
        download a non-existent file.

        For our append-only operation log schema, we insert a 'remove' operation with a
        new USN, delete from current state, and update meta counts + last_usn.
        """
        try:
            # Lookup current entry for file to adjust counts
            row = self.db.execute(
                "SELECT size FROM media_current WHERE fname = ?",
                (filename,),
            ).fetchone()

            if not row:
                # Nothing to do if not currently present
                return

            file_size = row[0] if row and row[0] is not None else 0

            current_usn = self.last_usn()
            new_usn = current_usn + 1
            current_time = int(time.time())

            # Append a remove op so future media_changes advertise deletion
            self.db.execute(
                """
                INSERT INTO media_operations (usn, operation, fname, csum, size, timestamp)
                VALUES (?, 'remove', ?, NULL, NULL, ?)
                """,
                (new_usn, filename, current_time),
            )

            # Remove from current state
            self.db.execute("DELETE FROM media_current WHERE fname = ?", (filename,))

            # Update meta counters and last_usn
            if file_size and isinstance(file_size, int):
                self.db.execute(
                    """
                    UPDATE meta SET 
                        total_bytes = total_bytes - ?,
                        total_nonempty_files = total_nonempty_files - 1,
                        last_usn = ?
                    """,
                    (file_size, new_usn),
                )
            else:
                self.db.execute("UPDATE meta SET last_usn = ?", (new_usn,))

            self.db.commit()
            logger.warning(
                f"🔧 FORGET MISSING: Recorded removal op for missing file '{filename}', advanced USN to {new_usn}"
            )
        except Exception as e:
            # Rollback on error to keep DB consistent
            try:
                self.db.rollback()
            except Exception:
                pass
            logger.error(f"Failed to forget missing file '{filename}': {e}")
            raise
    
    def register_uploaded_change(self, filename: str, data: Optional[bytes], 
                               sha1_hex: Optional[str]) -> Tuple[str, int]:
        """Register an uploaded file change in the operation log (correct Anki protocol)."""
        current_usn = self.last_usn()
        new_usn = current_usn + 1
        current_time = int(time.time())
        
        logger.debug(f"🔍 OPERATION LOG: Processing {filename}, current_usn={current_usn}, new_usn={new_usn}")
        
        if data is None:
            # File deletion - add REMOVE operation to log
            existing = self.db.execute(
                "SELECT csum, size FROM media_current WHERE fname = ?", (filename,)
            ).fetchone()
            
            if existing:
                # Add REMOVE operation to log
                self.db.execute("""
                    INSERT INTO media_operations (usn, operation, fname, csum, size, timestamp)
                    VALUES (?, 'remove', ?, NULL, NULL, ?)
                """, (new_usn, filename, current_time))
                
                # Remove from current state
                self.db.execute("DELETE FROM media_current WHERE fname = ?", (filename,))
                self._update_meta_after_deletion(existing[1])
                action = "removed"
            else:
                action = "already_deleted"
        else:
            # File addition/update - add ADD operation to log
            file_size = len(data)
            csum_bytes = bytes.fromhex(sha1_hex) if sha1_hex else hashlib.sha1(data).digest()
            mtime = int(time.time())
            
            # Verify checksum before any operations
            calculated_checksum = hashlib.sha1(data).digest()
            if csum_bytes != calculated_checksum:
                raise ValueError(f"Checksum mismatch for {filename}: expected {csum_bytes.hex()}, got {calculated_checksum.hex()}")
            
            existing = self.db.execute(
                "SELECT csum, size FROM media_current WHERE fname = ?", (filename,)
            ).fetchone()
            
            if existing and existing[0] == csum_bytes:
                action = "identical"
            else:
                try:
                    # Add ADD operation to log
                    self.db.execute("""
                        INSERT INTO media_operations (usn, operation, fname, csum, size, timestamp)
                        VALUES (?, 'add', ?, ?, ?, ?)
                    """, (new_usn, filename, csum_bytes, file_size, current_time))
                    
                    # Update current state
                    self.db.execute("""
                        INSERT OR REPLACE INTO media_current (fname, csum, size, added_usn, mtime)
                        VALUES (?, ?, ?, ?, ?)
                    """, (filename, csum_bytes, file_size, new_usn, mtime))
                    
                    if existing:
                        self._update_meta_after_replacement(existing[1], file_size)
                        action = "replaced"
                    else:
                        self._update_meta_after_addition(file_size)
                        action = "added"
                    
                    logger.debug(f"Operation log entry created for {filename}: action={action}")
                    
                except Exception as db_error:
                    # Database operation failed - rollback and re-raise
                    self.db.rollback()
                    logger.error(f"Operation log failed for {filename}: {db_error}")
                    raise ValueError(f"Operation log failed for {filename}: {db_error}")
        
        # Update USN only for actual changes (this maintains the operation sequence)
        if action != "identical" and action != "already_deleted":
            self.db.execute("UPDATE meta SET last_usn = ?", (new_usn,))
            logger.debug(f"🔍 OPERATION LOG: Advanced USN from {current_usn} to {new_usn} for {filename}")
        
        # Commit all database changes - this makes the operation atomic
        self.db.commit()
        logger.debug(f"Operation log entry committed for {filename}: action={action}")
        
        final_usn = new_usn if action not in ("identical", "already_deleted") else current_usn
        logger.debug(f"🔍 OPERATION LOG: Returning action={action}, usn={final_usn} for {filename}")
        return action, final_usn
    
    def _update_meta_after_addition(self, file_size: int):
        """Update meta table after file addition."""
        self.db.execute("""
            UPDATE meta SET 
                total_bytes = total_bytes + ?,
                total_nonempty_files = total_nonempty_files + 1
        """, (file_size,))
    
    def _update_meta_after_replacement(self, old_size: int, new_size: int):
        """Update meta table after file replacement."""
        self.db.execute("""
            UPDATE meta SET total_bytes = total_bytes - ? + ?
        """, (old_size, new_size))
    
    def _update_meta_after_deletion(self, file_size: int):
        """Update meta table after file deletion."""
        self.db.execute("""
            UPDATE meta SET 
                total_bytes = total_bytes - ?,
                total_nonempty_files = total_nonempty_files - 1
        """, (file_size,))
    
    
    def close(self):
        """Close the database connection."""
        if self.db:
            self.db.close()
            self.db = None


class ServerMediaManager:
    """Modern server-side media manager compatible with Anki's latest protocol."""
    
    def __init__(self, user_folder: str):
        self.user_folder = Path(user_folder)
        
        # Media files should be stored in user-specific folder, not global
        self.media_folder = self.user_folder / "collection.media"
        self.media_folder.mkdir(exist_ok=True)
        
        # Use user-specific database path to match what sync expects
        db_path = str(self.user_folder / "collection.media.server.db")
        self.db = ServerMediaDatabase(db_path)
        
        logger.info(f"Initialized media manager for user folder: {user_folder}")
        logger.info(f"Media folder: {self.media_folder}")
        logger.info(f"Database path: {db_path}")
    
    def last_usn(self) -> int:
        """Get the last media USN."""
        usn = self.db.last_usn()
        logger.debug(f"🔍 MEDIA USN DEBUG: Current server media USN is {usn}")
        return usn
    
    def media_changes_chunk(self, after_usn: int) -> List[Dict[str, Any]]:
        """Get media changes after the specified USN in the format expected by clients.

        Additionally, proactively fix server DB entries that advertise files as present
        when they are missing on disk. This avoids a later 409 during downloadFiles and
        provides a smoother UX.
        """
        # First pass: read current operation log batch
        changes = self.db.media_changes_chunk(after_usn)

        # Detect invalid 'add' entries where the file is missing on disk
        missing_adds: List[str] = []
        for fname, _usn, csum in changes:
            if csum and isinstance(csum, str) and len(csum) > 0:
                # Treat as 'add' operation
                if not (self.media_folder / fname).exists():
                    missing_adds.append(fname)

        # If we found missing files, correct the DB now and re-fetch the batch so
        # clients can see the resulting 'remove' operations instead of hitting 409 later
        if missing_adds:
            for fname in missing_adds:
                try:
                    self.db.forget_missing_file(fname)
                except Exception as e:
                    logger.error(f"Failed to forget missing file during media_changes for '{fname}': {e}")

            # Re-fetch after applying corrections so the new remove ops are included
            changes = self.db.media_changes_chunk(after_usn)

            # As a safety net, filter out any remaining invalid adds in case the remove
            # fell outside the current 250 limit. This prevents the client from trying to
            # download a missing file in this cycle.
            filtered: List[Tuple[str, int, str]] = []
            for fname, usn, csum in changes:
                if csum and isinstance(csum, str) and len(csum) > 0:
                    if not (self.media_folder / fname).exists():
                        # Drop invalid add from this response
                        continue
                filtered.append((fname, usn, csum))
            changes = filtered

        return [
            {"fname": fname, "usn": usn, "sha1": (csum.lower() if isinstance(csum, str) else csum)}
            for fname, usn, csum in changes
        ]
    
    def sanity_check(self, client_file_count: int) -> str:
        """Perform media sanity check."""
        server_count = self.db.nonempty_file_count()
        logger.info(f"Media sanity check: client={client_file_count}, server={server_count}")
        
        if server_count != client_file_count:
            logger.warning(f"File count mismatch detected! Client reports {client_file_count} files, server has {server_count}")
            
            # Let's check what files are actually on disk vs in database
            actual_files_on_disk = 0
            if self.media_folder.exists():
                try:
                    actual_files_on_disk = len([f for f in self.media_folder.iterdir() 
                                              if f.is_file() and not f.name.startswith('.')])
                    logger.info(f"Actual files on disk: {actual_files_on_disk}")
                except Exception as e:
                    logger.warning(f"Could not count files on disk: {e}")
            
            logger.info("Recalculating server count...")
            server_count = self.db.recalculate_file_count()
            logger.info(f"After recalculation: client={client_file_count}, server={server_count}, disk={actual_files_on_disk}")
            
            # If still mismatched, this suggests the client has files that weren't uploaded properly
            if server_count != client_file_count:
                logger.error(f"Persistent count mismatch after recalculation!")
                logger.error(f"This suggests {client_file_count - server_count} files failed to upload properly")
        
        return "OK" if server_count == client_file_count else "FAILED"
    
    def process_uploaded_changes(self, zip_data: bytes) -> Dict[str, Any]:
        """Process uploaded media changes from zip file."""
        try:
            extracted = self._unzip_and_validate_files(zip_data)
            processed = 0
            skipped = 0
            added = 0
            replaced = 0
            removed = 0
            identical = 0
            
            logger.info(f"Processing {len(extracted)} extracted changes from upload")
            
            for change in extracted:
                filename = change["filename"]
                data = change.get("data")
                sha1_hex = change.get("sha1")
                
                # Normalize filename
                filename = self._normalize_filename(filename)
                
                # Validate filename length
                if len(filename) > MAX_MEDIA_FILENAME_LENGTH_SERVER:
                    logger.warning(f"Filename too long, skipping: {filename}")
                    skipped += 1
                    continue
                
                # Process the change with atomic filesystem operations
                try:
                    action, new_usn = self._process_media_change_atomically(filename, data, sha1_hex)
                    
                    if action == "added":
                        added += 1
                    elif action == "replaced":
                        replaced += 1
                    elif action == "removed":
                        removed += 1
                    elif action == "identical":
                        identical += 1
                    
                except Exception as e:
                    logger.error(f"Failed to process media change for {filename}: {e}")
                    # Don't let one failed file break the entire upload
                    skipped += 1
                    continue
                
                processed += 1
            
            logger.info(f"Upload processing complete: processed={processed}, skipped={skipped}")
            logger.info(f"Actions: added={added}, replaced={replaced}, removed={removed}, identical={identical}")
            logger.info(f"Current server USN: {self.db.last_usn()}")
            
            return {
                "processed": processed,
                "current_usn": self.db.last_usn()
            }
            
        except Exception as e:
            logger.error(f"Error processing uploaded changes: {e}")
            raise
    
    def zip_files_for_download(self, filenames: List[str]) -> bytes:
        """Create a zip file containing the requested media files."""
        import io
        
        logger.info(f"Creating zip for {len(filenames)} requested files")
        logger.info(f"Media folder: {self.media_folder}")
        
        zip_buffer = io.BytesIO()
        file_map = {}
        found_files = 0
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for i, filename in enumerate(filenames):
                file_path = self.media_folder / filename
                
                if file_path.exists() and file_path.is_file():
                    # Add file to zip with numeric name
                    zip_name = str(i)
                    zf.write(file_path, zip_name)
                    file_map[zip_name] = filename
                    found_files += 1
                    logger.info(f"Added file {found_files}: {filename} -> {zip_name}")
                    
                    # Check size limits
                    if zip_buffer.tell() > MEDIA_SYNC_TARGET_ZIP_BYTES:
                        break
                    
                    if len(file_map) >= MAX_MEDIA_FILES_IN_ZIP:
                        break
                else:
                    # The server's DB claims the file exists, but it's missing on disk.
                    # Update DB to reflect removal and abort with a conflict so the client
                    # can resync cleanly.
                    try:
                        self.db.forget_missing_file(filename)
                    except Exception as e:
                        # If DB update fails, still raise a conflict to stop the loop
                        logger.error(f"Failed to update DB for missing file '{filename}': {e}")
                    logger.warning(f"Requested file not found: {filename} (path: {file_path}); raising conflict")
                    raise MediaConflict(f"requested a file that doesn't exist: {filename}")
            
            # Add metadata file with proper mapping
            # The client uses this to map zip entries back to filenames
            zf.writestr("_meta", json.dumps(file_map))
            logger.info(f"Created zip with {found_files} files out of {len(filenames)} requested")
            logger.info(f"Metadata: {file_map}")
        
        return zip_buffer.getvalue()
    
    def _unzip_and_validate_files(self, zip_data: bytes) -> List[Dict[str, Any]]:
        """Extract and validate files from uploaded zip."""
        changes = []
        
        with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zf:
            # Read metadata
            try:
                meta_data = zf.read("_meta").decode('utf-8')
                meta = json.loads(meta_data)
                logger.info(f"Metadata structure: {meta}")
                logger.info(f"Metadata type: {type(meta)}")
            except (KeyError, json.JSONDecodeError) as e:
                raise ValueError(f"Invalid or missing metadata in zip: {e}")
            
            # Validate zip size
            total_size = sum(info.file_size for info in zf.infolist())
            if total_size > MAX_INDIVIDUAL_MEDIA_FILE_SIZE:
                raise ValueError(f"Zip file too large: {total_size} bytes")
            
            # Handle different metadata formats
            if isinstance(meta, list):
                # Modern format: list of [filename, zip_name]
                for entry in meta:
                    if not isinstance(entry, list) or len(entry) != 2:
                        logger.warning(f"Invalid metadata entry format: {entry}")
                        continue
                    
                    filename, zip_name = entry
                    
                    if zip_name is None:
                        # File deletion - zip_name is None
                        changes.append({
                            "filename": filename,
                            "data": None,
                            "sha1": None
                        })
                        logger.debug(f"Marked for deletion: {filename}")
                    elif zip_name in zf.namelist():
                        # File addition/update - zip_name should exist in zip
                        file_data = zf.read(zip_name)
                        
                        # Validate file size
                        if len(file_data) > MAX_INDIVIDUAL_MEDIA_FILE_SIZE:
                            logger.warning(f"File too large, skipping: {filename}")
                            continue
                        
                        # Calculate SHA1
                        sha1_hex = hashlib.sha1(file_data).hexdigest()
                        
                        changes.append({
                            "filename": filename,
                            "data": file_data,
                            "sha1": sha1_hex
                        })
                        logger.debug(f"Marked for addition/update: {filename}")
                    else:
                        logger.warning(f"Zip entry not found for file: {filename} (zip_name: {zip_name})")
            elif isinstance(meta, dict):
                # Legacy format: dict mapping zip_name -> filename
                for zip_name, filename in meta.items():
                    if zip_name == "_meta":
                        continue
                    
                    try:
                        if isinstance(filename, list) and len(filename) >= 2:
                            # Format: [filename, ordinal] where ordinal=0 means deletion
                            actual_filename, ordinal = filename[0], filename[1]
                            
                            if ordinal == 0:
                                # File deletion
                                changes.append({
                                    "filename": actual_filename,
                                    "data": None,
                                    "sha1": None
                                })
                            else:
                                # File addition - should have corresponding zip entry
                                if zip_name in zf.namelist():
                                    file_data = zf.read(zip_name)
                                    
                                    # Validate file size
                                    if len(file_data) > MAX_INDIVIDUAL_MEDIA_FILE_SIZE:
                                        logger.warning(f"File too large, skipping: {actual_filename}")
                                        continue
                                    
                                    # Calculate SHA1
                                    sha1_hex = hashlib.sha1(file_data).hexdigest()
                                    
                                    changes.append({
                                        "filename": actual_filename,
                                        "data": file_data,
                                        "sha1": sha1_hex
                                    })
                        else:
                            # Simple filename mapping (legacy format)
                            if zip_name in zf.namelist():
                                file_data = zf.read(zip_name)
                                sha1_hex = hashlib.sha1(file_data).hexdigest()
                                
                                changes.append({
                                    "filename": filename,
                                    "data": file_data,
                                    "sha1": sha1_hex
                                })
                    
                    except Exception as e:
                        logger.warning(f"Error processing zip entry {zip_name}: {e}")
                        continue
            else:
                logger.error(f"Unexpected metadata format: {type(meta)}")
                raise ValueError(f"Unsupported metadata format: {type(meta)}")
        
        return changes
    
    def _process_media_change_atomically(self, filename: str, data: Optional[bytes], 
                                       sha1_hex: Optional[str]) -> Tuple[str, int]:
        """Process a media change with atomic filesystem operations."""
        if data is None:
            # File deletion - handle filesystem and database atomically
            action, new_usn = self.db.register_uploaded_change(filename, data, sha1_hex)
            
            if action == "removed":
                # Remove file from filesystem after successful database update
                file_path = self.media_folder / filename
                if file_path.exists():
                    try:
                        file_path.unlink()
                        logger.debug(f"Removed file: {filename}")
                    except Exception as e:
                        logger.warning(f"Could not remove file {filename}: {e}")
                        # File removal failed, but database was updated - this is not critical
                        # The file will be orphaned but won't cause sync issues
            
            return action, new_usn
        else:
            # File addition/update - use temporary files for atomic operations
            temp_file_path = None
            final_file_path = self.media_folder / filename
            
            try:
                # Step 1: Create temporary file with unique name
                import tempfile
                temp_fd, temp_file_path = tempfile.mkstemp(
                    suffix=f"_{filename}", 
                    dir=self.media_folder, 
                    prefix=".tmp_"
                )
                
                # Step 2: Write data to temporary file
                with os.fdopen(temp_fd, 'wb') as temp_file:
                    temp_file.write(data)
                    temp_file.flush()
                    os.fsync(temp_file.fileno())  # Force write to disk
                
                # Step 3: Verify file was written correctly
                if not os.path.exists(temp_file_path):
                    raise IOError(f"Temporary file was not created: {temp_file_path}")
                
                actual_size = os.path.getsize(temp_file_path)
                if actual_size != len(data):
                    raise IOError(f"File size mismatch: expected {len(data)}, got {actual_size}")
                
                # Step 4: Verify checksum of written file
                with open(temp_file_path, 'rb') as verify_file:
                    written_data = verify_file.read()
                    if written_data != data:
                        raise IOError(f"File content verification failed for {filename}")
                
                # Step 5: Atomically move temporary file to final location BEFORE database update
                # This ensures filesystem is consistent before database claims the file exists
                try:
                    # Remove existing file if it exists (for replacement)
                    if final_file_path.exists():
                        final_file_path.unlink()
                    
                    # Atomic move operation
                    os.rename(temp_file_path, str(final_file_path))
                    temp_file_path = None  # Successfully moved, don't clean up
                    
                    logger.debug(f"Filesystem write completed for {filename} ({len(data)} bytes)")
                    
                except Exception as move_error:
                    logger.error(f"Failed to move file {filename}: {move_error}")
                    raise IOError(f"Atomic file move failed for {filename}: {move_error}")
                
                # Step 6: Update database only AFTER successful filesystem operation
                # This prevents race condition where database thinks file exists but filesystem doesn't have it
                action, new_usn = self.db.register_uploaded_change(filename, data, sha1_hex)
                
                return action, new_usn
                
            except Exception as e:
                logger.error(f"Atomic media operation failed for {filename}: {e}")
                raise
            
            finally:
                # Clean up temporary file if it still exists
                if temp_file_path and os.path.exists(temp_file_path):
                    try:
                        os.unlink(temp_file_path)
                        logger.debug(f"Cleaned up temporary file: {temp_file_path}")
                    except Exception as cleanup_error:
                        logger.warning(f"Could not clean up temporary file {temp_file_path}: {cleanup_error}")
    
    def _normalize_filename(self, filename: str) -> str:
        """Normalize filename for cross-platform compatibility."""
        # Perform unicode normalization
        if hasattr(anki.utils, 'is_mac') and anki.utils.is_mac:
            filename = unicodedata.normalize("NFD", filename)
        else:
            filename = unicodedata.normalize("NFC", filename)
        
        # Remove any path separators for security
        filename = os.path.basename(filename)
        
        return filename
    
    def close(self):
        """Close the media manager and database."""
        if self.db:
            self.db.close()


class MediaSyncHandler:
    """Modern media sync handler implementing the latest Anki protocol."""
    
    def __init__(self, media_manager: ServerMediaManager, session):
        self.media_manager = media_manager
        self.session = session
    
    def begin(self, client_version: str = "", session_key: str = "") -> Dict[str, Any]:
        """
        Initialize media sync session.
        Updated for modern Anki protocol compatibility.
        """
        if not client_version:
            raise ValueError("Client version is required")
        
        # Modern response format based on Anki reference: 
        # rslib/src/sync/media/begin.rs - SyncBeginResponse
        # The 'sk' field should contain the host key, not a session key
        
        # Return the same host key that was used for authentication
        return {
            "data": {
                "usn": self.media_manager.last_usn(),
                # Return the host key in 'sk' field for compatibility
                "sk": session_key
            },
            "err": ""
        }
    
    def media_changes(self, last_usn: int) -> Dict[str, Any]:
        """Get media operations since the specified USN from operation log."""
        try:
            operations = self.media_manager.media_changes_chunk(last_usn)
            current_server_usn = self.media_manager.last_usn()
            
            # Convert operation log to client format: [fname, usn, sha1]
            operation_list = [
                [op['fname'], op['usn'], op['sha1']] for op in operations
            ]
            
            logger.info(f"🔍 OPERATION LOG: client_last_usn={last_usn}, server_usn={current_server_usn}, operations_count={len(operation_list)}")
            if operation_list:
                logger.info(f"🔍 OPERATION LOG: First few operations: {operation_list[:3]}")
                logger.info(f"🔍 OPERATION LOG: Last operation USN: {operation_list[-1][1]}")
            
            # This should now work correctly: client expects operations from last_usn+1 to current_usn
            # With proper operation log: client_last_usn + operations_received = server_usn ✅
            if operation_list:
                expected_final_usn = last_usn + len(operation_list)
                if expected_final_usn <= current_server_usn:
                    logger.info(f"✅ OPERATION LOG MATH: {last_usn} + {len(operation_list)} = {expected_final_usn} ≤ {current_server_usn}")
                else:
                    logger.warning(f"⚠️ OPERATION LOG MATH: {last_usn} + {len(operation_list)} = {expected_final_usn} > {current_server_usn}")
            
            return {
                "data": operation_list,
                "err": ""
            }
        except Exception as e:
            logger.error(f"Error getting media changes: {e}")
            return {
                "data": [],
                "err": str(e)
            }
    
    def upload_changes(self, zip_data: bytes) -> Dict[str, Any]:
        """Process uploaded media changes."""
        try:
            logger.info(f"🔍 MEDIA UPLOAD DEBUG: Processing {len(zip_data)} bytes of uploaded changes")
            result = self.media_manager.process_uploaded_changes(zip_data)
            
            logger.info(f"🔍 MEDIA UPLOAD DEBUG: Processed {result['processed']} changes, server USN now {result['current_usn']}")
            
            return {
                "data": [result["processed"], result["current_usn"]],  # Tuple format expected by client
                "err": ""
            }
        except Exception as e:
            logger.error(f"Error uploading changes: {e}")
            return {
                "data": [0, self.media_manager.last_usn()],  # Tuple format for error case too
                "err": str(e)
            }
    
    def download_files(self, files: List[str]) -> bytes:
        """Download requested media files as a zip."""
        try:
            logger.info(f"Download request for {len(files)} files: {files[:10]}...")  # Log first 10 files
            result = self.media_manager.zip_files_for_download(files)
            logger.info(f"Download response size: {len(result)} bytes")
            return result
        except MediaConflict:
            # Propagate so the caller can translate into an HTTP 409
            raise
        except Exception as e:
            logger.error(f"Error downloading files: {e}")
            # Return empty zip on error
            import io
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w') as zf:
                zf.writestr("_meta", json.dumps({}))
            return zip_buffer.getvalue()
    
    def media_sanity(self, local_count: int) -> Dict[str, Any]:
        """Perform media sanity check."""
        try:
            result = self.media_manager.sanity_check(local_count)
            # Return the correct enum values expected by client
            response_value = "OK" if result == "OK" else "mediaSanity"
            return {
                "data": response_value,
                "err": ""
            }
        except Exception as e:
            logger.error(f"Error in media sanity check: {e}")
            return {
                "data": "mediaSanity",  # Failed sanity check
                "err": str(e)
            } 