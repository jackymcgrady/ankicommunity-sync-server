# -*- coding: utf-8 -*-
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import os
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
        else:
            self._upgrade_schema()
    
    def _create_schema(self):
        """Create the modern media database schema."""
        self.db.executescript("""
            CREATE TABLE media (
                fname TEXT NOT NULL PRIMARY KEY,
                csum BLOB NOT NULL,
                size INTEGER NOT NULL,
                usn INTEGER NOT NULL,
                mtime INTEGER NOT NULL
            );
            
            CREATE INDEX ix_usn ON media (usn);
            
            CREATE TABLE meta (
                last_usn INTEGER NOT NULL,
                total_bytes INTEGER NOT NULL,
                total_nonempty_files INTEGER NOT NULL
            );
            
            INSERT INTO meta (last_usn, total_bytes, total_nonempty_files) 
            VALUES (0, 0, 0);
            
            PRAGMA user_version = 4;
        """)
        self.db.commit()
        logger.info("Created new media database with modern schema")
    
    def _upgrade_schema(self):
        """Upgrade legacy media database to modern schema."""
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        
        if version < 4:
            logger.info(f"Upgrading media database from version {version} to 4")
            
            # Check if we have legacy schema
            tables = self.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = [t[0] for t in tables]
            
            if 'media' in table_names:
                # Check current schema
                columns = self.db.execute("PRAGMA table_info(media)").fetchall()
                column_names = [c[1] for c in columns]
                
                if 'csum' in column_names and 'size' not in column_names:
                    # Legacy schema - upgrade it
                    self.db.executescript("""
                        BEGIN EXCLUSIVE;
                        
                        ALTER TABLE media RENAME TO media_tmp;
                        
                        CREATE TABLE media (
                            fname TEXT NOT NULL PRIMARY KEY,
                            csum BLOB NOT NULL,
                            size INTEGER NOT NULL,
                            usn INTEGER NOT NULL,
                            mtime INTEGER NOT NULL
                        );
                        
                        INSERT INTO media (fname, csum, size, usn, mtime)
                        SELECT fname, 
                               CASE WHEN csum IS NULL THEN X'' ELSE csum END,
                               0,  -- size unknown for legacy files
                               usn,
                               CAST(strftime('%s', 'now') AS INTEGER)
                        FROM media_tmp 
                        WHERE csum IS NOT NULL;
                        
                        DROP TABLE media_tmp;
                        CREATE INDEX ix_usn ON media (usn);
                        
                        -- Create or update meta table
                        DROP TABLE IF EXISTS meta;
                        CREATE TABLE meta (
                            last_usn INTEGER NOT NULL,
                            total_bytes INTEGER NOT NULL,
                            total_nonempty_files INTEGER NOT NULL
                        );
                        
                        INSERT INTO meta (last_usn, total_bytes, total_nonempty_files)
                        SELECT COALESCE(MAX(usn), 0),
                               0,  -- total_bytes unknown for legacy
                               COUNT(*)
                        FROM media WHERE size >= 0;
                        
                        PRAGMA user_version = 4;
                        COMMIT;
                    """)
                    logger.info("Successfully upgraded legacy media database")
            else:
                # No existing media table, create new schema
                self._create_schema()
    
    def last_usn(self) -> int:
        """Get the last USN from the database."""
        result = self.db.execute("SELECT last_usn FROM meta").fetchone()
        return result[0] if result else 0
    
    def media_changes_chunk(self, after_usn: int) -> List[Tuple[str, int, str]]:
        """Get media changes after the specified USN."""
        changes = self.db.execute("""
            SELECT fname, usn, hex(csum) 
            FROM media 
            WHERE usn > ? 
            ORDER BY usn 
            LIMIT 250
        """, (after_usn,)).fetchall()
        
        return [(fname, usn, csum) for fname, usn, csum in changes]
    
    def nonempty_file_count(self) -> int:
        """Get count of non-empty files."""
        result = self.db.execute("SELECT total_nonempty_files FROM meta").fetchone()
        return result[0] if result else 0
    
    def register_uploaded_change(self, filename: str, data: Optional[bytes], 
                               sha1_hex: Optional[str]) -> Tuple[str, int]:
        """Register an uploaded file change and return action taken and new USN."""
        current_usn = self.last_usn()
        new_usn = current_usn + 1
        
        if data is None:
            # File deletion
            existing = self.db.execute(
                "SELECT csum, size FROM media WHERE fname = ?", (filename,)
            ).fetchone()
            
            if existing:
                self.db.execute("DELETE FROM media WHERE fname = ?", (filename,))
                self._update_meta_after_deletion(existing[1])
                action = "removed"
            else:
                action = "already_deleted"
        else:
            # File addition/update
            file_size = len(data)
            csum_bytes = bytes.fromhex(sha1_hex) if sha1_hex else hashlib.sha1(data).digest()
            mtime = int(time.time())
            
            existing = self.db.execute(
                "SELECT csum, size FROM media WHERE fname = ?", (filename,)
            ).fetchone()
            
            if existing and existing[0] == csum_bytes:
                action = "identical"
            else:
                self.db.execute("""
                    INSERT OR REPLACE INTO media (fname, csum, size, usn, mtime)
                    VALUES (?, ?, ?, ?, ?)
                """, (filename, csum_bytes, file_size, new_usn, mtime))
                
                if existing:
                    self._update_meta_after_replacement(existing[1], file_size)
                    action = "replaced"
                else:
                    self._update_meta_after_addition(file_size)
                    action = "added"
        
        if action != "identical" and action != "already_deleted":
            self.db.execute("UPDATE meta SET last_usn = ?", (new_usn,))
        
        self.db.commit()
        return action, new_usn if action not in ("identical", "already_deleted") else current_usn
    
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
        self.media_folder = self.user_folder / "media"
        self.media_folder.mkdir(exist_ok=True)
        
        db_path = str(self.user_folder / "media.db")
        self.db = ServerMediaDatabase(db_path)
        
        logger.info(f"Initialized media manager for user folder: {user_folder}")
    
    def last_usn(self) -> int:
        """Get the last media USN."""
        return self.db.last_usn()
    
    def media_changes_chunk(self, after_usn: int) -> List[Dict[str, Any]]:
        """Get media changes after the specified USN in the format expected by clients."""
        changes = self.db.media_changes_chunk(after_usn)
        return [
            {"fname": fname, "usn": usn, "sha1": csum}
            for fname, usn, csum in changes
        ]
    
    def sanity_check(self, client_file_count: int) -> str:
        """Perform media sanity check."""
        server_count = self.db.nonempty_file_count()
        return "OK" if server_count == client_file_count else "FAILED"
    
    def process_uploaded_changes(self, zip_data: bytes) -> Dict[str, Any]:
        """Process uploaded media changes from zip file."""
        try:
            extracted = self._unzip_and_validate_files(zip_data)
            processed = 0
            
            for change in extracted:
                filename = change["filename"]
                data = change.get("data")
                sha1_hex = change.get("sha1")
                
                # Normalize filename
                filename = self._normalize_filename(filename)
                
                # Validate filename length
                if len(filename) > MAX_MEDIA_FILENAME_LENGTH_SERVER:
                    logger.warning(f"Filename too long, skipping: {filename}")
                    continue
                
                # Process the change
                action, new_usn = self.db.register_uploaded_change(filename, data, sha1_hex)
                
                if action in ("added", "replaced") and data:
                    # Write file to disk
                    file_path = self.media_folder / filename
                    with open(file_path, "wb") as f:
                        f.write(data)
                    logger.debug(f"Wrote file: {filename} ({len(data)} bytes)")
                
                elif action == "removed":
                    # Remove file from disk
                    file_path = self.media_folder / filename
                    if file_path.exists():
                        file_path.unlink()
                        logger.debug(f"Removed file: {filename}")
                
                processed += 1
            
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
        
        zip_buffer = io.BytesIO()
        file_map = {}
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for i, filename in enumerate(filenames):
                file_path = self.media_folder / filename
                
                if file_path.exists() and file_path.is_file():
                    # Add file to zip with numeric name
                    zip_name = str(i)
                    zf.write(file_path, zip_name)
                    file_map[zip_name] = filename
                    
                    # Check size limits
                    if zip_buffer.tell() > MEDIA_SYNC_TARGET_ZIP_BYTES:
                        break
                    
                    if len(file_map) >= MAX_MEDIA_FILES_IN_ZIP:
                        break
                else:
                    logger.warning(f"Requested file not found: {filename}")
            
            # Add metadata file
            zf.writestr("_meta", json.dumps(file_map))
        
        return zip_buffer.getvalue()
    
    def _unzip_and_validate_files(self, zip_data: bytes) -> List[Dict[str, Any]]:
        """Extract and validate files from uploaded zip."""
        changes = []
        
        with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zf:
            # Read metadata
            try:
                meta_data = zf.read("_meta").decode('utf-8')
                meta = json.loads(meta_data)
            except (KeyError, json.JSONDecodeError) as e:
                raise ValueError(f"Invalid or missing metadata in zip: {e}")
            
            # Validate zip size
            total_size = sum(info.file_size for info in zf.infolist())
            if total_size > MAX_INDIVIDUAL_MEDIA_FILE_SIZE:
                raise ValueError(f"Zip file too large: {total_size} bytes")
            
            # Process each entry in metadata
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
        
        return changes
    
    def _normalize_filename(self, filename: str) -> str:
        """Normalize filename for cross-platform compatibility."""
        # Perform unicode normalization
        if hasattr(anki.utils, 'isMac') and anki.utils.isMac:
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
    
    def begin(self, client_version: str = "") -> Dict[str, Any]:
        """
        Initialize media sync session.
        Updated for modern Anki protocol compatibility.
        """
        if not client_version:
            raise ValueError("Client version is required")
        
        # Modern response format based on Anki reference: 
        # rslib/src/sync/media/begin.rs - SyncBeginResponse
        return {
            "data": {
                "usn": self.media_manager.last_usn(),
                # Modern clients expect 'sk' (session key) field
                # For compatibility, return the host key as session key
                "sk": self.session.skey if hasattr(self.session, 'skey') else ""
            },
            "err": ""
        }
    
    def media_changes(self, last_usn: int) -> Dict[str, Any]:
        """Get media changes since the specified USN."""
        try:
            changes = self.media_manager.media_changes_chunk(last_usn)
            
            # Convert to the format expected by clients: [fname, usn, sha1]
            change_list = [
                [change["fname"], change["usn"], change["sha1"]]
                for change in changes
            ]
            
            return {
                "data": change_list,
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
            result = self.media_manager.process_uploaded_changes(zip_data)
            
            return {
                "data": {
                    "processed": result["processed"],
                    "current_usn": result["current_usn"]
                },
                "err": ""
            }
        except Exception as e:
            logger.error(f"Error uploading changes: {e}")
            return {
                "data": {"processed": 0, "current_usn": self.media_manager.last_usn()},
                "err": str(e)
            }
    
    def download_files(self, files: List[str]) -> bytes:
        """Download requested media files as a zip."""
        try:
            return self.media_manager.zip_files_for_download(files)
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
            return {
                "data": result,
                "err": ""
            }
        except Exception as e:
            logger.error(f"Error in media sanity check: {e}")
            return {
                "data": "FAILED",
                "err": str(e)
            } 