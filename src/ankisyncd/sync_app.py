# ankisyncd - A personal Anki sync server
# Copyright (C) 2013 David Snopek
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import io
import gzip
import json
import logging
import os
import random
import re
import sys
import time
import unicodedata
import zipfile
import types
import zstandard as zstd
from webob import Response
from .user_sync_queue import get_user_sync_queue
from webob.exc import *
import urllib.parse
from functools import wraps
import anki
import anki.db
import anki.utils
# Import helper functions from Anki, handling old versions that expose
# `intTime`/`ids2str` with different casing.
from anki import utils as _anki_utils  # type: ignore

# `int_time` was introduced in newer Anki.  Older wheels (e.g. 2.1.35) only
# expose `intTime`.  Provide a fallback so the rest of the code can keep using
# `int_time` transparently.
if hasattr(_anki_utils, "int_time"):
    int_time = _anki_utils.int_time  # pylint: disable=invalid-name
else:  # pragma: no cover – legacy Anki <2.1.40
    int_time = _anki_utils.intTime  # type: ignore[attr-defined]

# Same story for `ids2str`, which has been stable but add a safeguard anyway.
ids2str = getattr(_anki_utils, "ids2str", getattr(_anki_utils, "ids2Str", None))

__all__ = ["int_time", "ids2str"]
from anki.consts import REM_CARD, REM_NOTE
from ankisyncd.full_sync import get_full_sync_manager
from ankisyncd.sessions import get_session_manager
from ankisyncd.sync import Syncer, SYNC_VER, SYNC_ZIP_SIZE, SYNC_ZIP_COUNT, SYNC_VERSION_MIN, SYNC_VERSION_MAX, SYNC_VERSION_09_V2_SCHEDULER, SYNC_VERSION_10_V2_TIMEZONE, is_sync_version_supported
from ankisyncd.users import get_user_manager
from .media_manager import ServerMediaManager, MediaSyncHandler
import threading

logger = logging.getLogger("ankisyncd")


# HTTP Exception Classes
class HTTPException(Exception):
    """Base class for HTTP exceptions."""
    def __init__(self, message=""):
        self.message = message
        super().__init__(message)


class HTTPBadRequest(HTTPException):
    """HTTP 400 Bad Request"""
    pass


class HTTPUnauthorized(HTTPException):
    """HTTP 401 Unauthorized"""
    pass


class HTTPForbidden(HTTPException):
    """HTTP 403 Forbidden"""
    pass


class HTTPNotFound(HTTPException):
    """HTTP 404 Not Found"""
    pass


class HTTPInternalServerError(HTTPException):
    """HTTP 500 Internal Server Error"""
    pass


class SyncCollectionHandler(Syncer):
    operations = [
        "meta",
        "applyChanges",
        "start",
        "applyGraves",
        "chunk",
        "applyChunk",
        "sanityCheck2",
        "finish",
    ]

    def __init__(self, col, session):
        # So that 'server' (the 3rd argument) can't get set
        super().__init__(col)
        self.session = session

    @staticmethod
    def _old_client(cv):
        """
        Check if the client version is too old to be supported.
        Updated to handle modern Anki client version formats.
        """
        if not cv:
            return False

        # Handle modern Anki client version format: "anki,VERSION (BUILDHASH),PLATFORM"
        # or legacy format: "ankidesktop,VERSION,PLATFORM"
        try:
            parts = cv.split(",")
            if len(parts) < 2:
                return False
                
            client = parts[0].strip()
            version_part = parts[1].strip()
            
            # Extract version from modern format like "2.1.66 (70506aeb)"
            if "(" in version_part and ")" in version_part:
                version = version_part.split("(")[0].strip()
            else:
                version = version_part
            
            # Handle version suffixes (alpha, beta, rc)
            note = {"alpha": 0, "beta": 0, "rc": 0}
            if "arch" not in version:
                for name in note.keys():
                    if name in version:
                        vs = version.split(name)
                        version = vs[0]
                        if len(vs) > 1 and vs[1].isdigit():
                            note[name] = int(vs[1])

            # Convert the version string, ignoring non-numeric suffixes
            version_nosuffix = re.sub(r"[^0-9.].*$", "", version)
            if not version_nosuffix:
                return False
                
            version_parts = version_nosuffix.split(".")
            version_int = []
            for part in version_parts:
                if part.isdigit():
                    version_int.append(int(part))
                else:
                    break

            # Check client-specific version requirements
            if client in ("ankidesktop", "anki"):
                # Anki Desktop: require 2.1.57+ for modern sync
                if len(version_int) >= 3:
                    return version_int < [2, 1, 57]
                elif len(version_int) >= 2:
                    return version_int < [2, 1]
                else:
                    return version_int < [2]
            elif client == "ankidroid":
                # AnkiDroid version checking
                if len(version_int) >= 2 and version_int[:2] == [2, 3]:
                    if note["alpha"]:
                        return note["alpha"] < 4
                else:
                    return version_int < [2, 2, 3]
            else:
                # Unknown client, assume current version
                return False
                
        except (ValueError, IndexError, AttributeError):
            # If we can't parse the version, assume it's current
            return False

        return False

    def meta(self, v=None, cv=None):
        """
        Modern meta response implementation compatible with Anki >=2.1.57.
        Based on Anki reference: rslib/src/sync/collection/meta.rs
        """
        # Check for old clients that need upgrade
        if self._old_client(cv):
            return Response(status=501)  # client needs upgrade
        
        # Validate sync version - use modern range checking
        if v is None:
            v = SYNC_VERSION_MIN  # Default to minimum supported version
            
        if not is_sync_version_supported(v):
            # Return HTTP 501 for unsupported versions (matches Anki reference)
            from webob.exc import HTTPNotImplemented
            raise HTTPNotImplemented("unsupported version")
        
        # Check scheduler compatibility
        if v < SYNC_VERSION_09_V2_SCHEDULER and self.col.schedVer() >= 2:
            return {
                "cont": False,
                "msg": "Your client does not support the v2 scheduler",
            }
        
        # Check timezone compatibility  
        if v < SYNC_VERSION_10_V2_TIMEZONE and hasattr(self.col, 'get_creation_utc_offset') and self.col.get_creation_utc_offset() is not None:
            return {
                "cont": False,
                "msg": "Your client does not support the new timezone handling.",
            }

        # Handle media connection properly based on collection type
        media_usn = 0
        try:
            if hasattr(self.col, 'media'):
                # Direct collection object - use media directly
                self.col.media.connect()
                media_usn = self.col.media.lastUsn()
            elif hasattr(self.col, 'execute'):
                # Collection wrapper - use execute method to access media
                def get_media_usn(col):
                    col.media.connect()
                    return col.media.lastUsn()
                media_usn = self.col.execute(get_media_usn, waitForReturn=True)
            else:
                # Fallback - assume media USN is 0
                logger.warning("Cannot access media from collection, using USN 0")
                media_usn = 0
        except Exception as e:
            logger.warning(f"Failed to get media USN: {e}, using 0")
            media_usn = 0
        
        # Get collection timestamps
        try:
            # Try modern method first
            if hasattr(self.col.db, 'scalar') and hasattr(self.col, 'crt'):
                collection_change = self.col.mod
                schema_change = self.scm()
            else:
                # Fallback for older Anki versions
                collection_change = self.col.mod
                schema_change = self.scm()
        except Exception:
            collection_change = self.col.mod
            schema_change = self.scm()
        
        # Check if collection is empty (has no cards)
        try:
            empty = self.col.db.scalar("SELECT 1 FROM cards LIMIT 1") is None
        except Exception:
            empty = False
        
        # Check for large collections that need one-way sync
        # Based on MAXIMUM_SYNC_PAYLOAD_BYTES_UNCOMPRESSED from Anki reference
        MAX_COLLECTION_SIZE = 100 * 1024 * 1024  # 100MB
        try:
            import os
            collection_path = self.col.path
            if os.path.exists(collection_path):
                collection_bytes = os.path.getsize(collection_path)
                if collection_bytes > MAX_COLLECTION_SIZE:
                    # Force one-way sync by updating schema timestamp
                    schema_change = anki.utils.int_time(1000)
            else:
                collection_bytes = 0
        except Exception:
            collection_bytes = 0

        # Build modern meta response
        meta_response = {
            "mod": collection_change,
            "scm": schema_change,
            "usn": self.col.usn(),
            "ts": anki.utils.int_time(),
            "media_usn": media_usn,
            "msg": "",
            "cont": True,
            "hostNum": 0,  # Deprecated in v11+ but kept for compatibility
            "empty": empty,
        }
        
        # Add username if available (modern clients expect this)
        if hasattr(self.session, 'name') and self.session.name:
            meta_response["uname"] = self.session.name
        
        return meta_response

    def usnLim(self):
        return "usn >= %d" % self.minUsn

    # ankidesktop >=2.1rc2 sends graves in applyGraves, but still expects
    # server-side deletions to be returned by start
    def start(
        self,
        minUsn,
        lnewer,
        graves={"cards": [], "notes": [], "decks": []},
        offset=None,
    ):
        # The offset para is passed  by client V2 scheduler,which is minutes_west.
        # Since now have not thorougly test the V2 scheduler, we leave this comments here, and
        # just enable the V2 scheduler in the serve code.

        self.maxUsn = self.col.usn()
        self.minUsn = minUsn
        self.lnewer = not lnewer
        #  fetch local/server graves
        lgraves = self.removed()
        #  handle AnkiDroid using old protocol
        # Only if Operations like deleting deck are performed on Ankidroid
        # can (client) graves is not None
        if graves is not None:
            self.apply_graves(graves, self.maxUsn)
        return lgraves

    def applyGraves(self, chunk):
        self.apply_graves(chunk, self.maxUsn)

    def applyChanges(self, changes):
        self.rchg = changes
        lchg = self.changes()
        # merge our side before returning
        self.mergeChanges(lchg, self.rchg)
        return lchg

    def sanityCheck2(self, client):
        client[0] = [0, 0, 0]
        server = self.sanityCheck()
        if client != server:
            logger.info(f"sanity check failed with server: {server} client: {client}")
            return dict(status="bad", c=client, s=server)
        return dict(status="ok")

    def finish(self):
        """Finalize sync and ensure the on-disk collection is fully consolidated.

        A standard Anki client calls the *finish* operation as the final step of a
        sync session.  At this point the server-side collection might still have
        pending transactions in its WAL file.  If we immediately serve the
        collection back to another client (e.g. at the start of the next sync
        session or when downloading the entire collection), the main
        `collection.anki2` file could be only a few KiB in size and miss most of
        the recent changes – they would live exclusively in the WAL file.  Some
        clients refuse to open such a database and will prompt for a full
        upload, breaking the seamless sync experience.

        To avoid this we force an explicit WAL checkpoint **and** invoke
        `Collection.consolidate()` (available in modern Anki) or fall back to a
        `VACUUM` if the consolidated API is not present.  This merges WAL
        changes back into the main database file, truncates the WAL, and
        guarantees the collection can be opened on its own.
        """

        # Run the default finish logic (updates mod/ls/usn & saves).
        now = super().finish(anki.utils.int_time(1000))

        # Attempt to consolidate the collection so that all WAL changes are
        # flushed into the main DB file.
        try:
            if hasattr(self.col, "consolidate") and callable(self.col.consolidate):
                # Modern Anki provides this helper which runs VACUUM + ANALYZE
                # and rewrites the DB without requiring extra pragmas.
                self.col.consolidate()
            else:
                # Fallback: manual WAL checkpoint + VACUUM.
                self.col.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                self.col.db.execute("VACUUM")
            # Ensure writes are committed.
            self.col.db.commit()
        except Exception as e:
            # Consolidation failures should not abort the sync – just log.
            logger.warning(f"Collection consolidation failed: {e}")

        return now

    # This function had to be put here in its entirety because Syncer.removed()
    # doesn't use self.usnLim() (which we override in this class) in queries.
    # "usn=-1" has been replaced with "usn >= ?", self.minUsn by hand.
    def removed(self):
        cards = []
        notes = []
        decks = []

        curs = self.col.db.execute(
            "select oid, type from graves where usn >= ?", self.minUsn
        )

        for oid, type in curs:
            if type == REM_CARD:
                cards.append(oid)
            elif type == REM_NOTE:
                notes.append(oid)
            else:
                decks.append(oid)

        return dict(cards=cards, notes=notes, decks=decks)

    def getModels(self):
        return [m for m in self.col.models.all() if m["usn"] >= self.minUsn]

    def getDecks(self):
        return [
            [g for g in self.col.decks.all() if g["usn"] >= self.minUsn],
            [g for g in self.col.decks.all_config() if g["usn"] >= self.minUsn],
        ]

    def getTags(self):
        return [t for t, usn in self.allItems() if usn >= self.minUsn]


class SyncUserSession:
    def __init__(self, name, path, collection_manager, setup_new_collection=None):
        self.skey = self._generate_session_key()
        self.name = name
        self.path = path
        self.collection_manager = collection_manager
        self.setup_new_collection = setup_new_collection
        self.version = None
        self.client_version = None
        self.created = time.time()
        self.collection_handler = None
        self.media_handler = None
        self.media_manager = None

        # make sure the user path exists
        if not os.path.exists(path):
            os.mkdir(path)

    def _generate_session_key(self):
        return anki.utils.checksum(str(random.random()))[:8]

    def get_collection_path(self):
        return os.path.realpath(os.path.join(self.path, "collection.anki2"))

    def get_thread(self):
        """
        Returns a simple thread executor for this session.
        """
        if not hasattr(self, '_thread_executor'):
            self._thread_executor = SimpleThreadExecutor()
        return self._thread_executor

    def get_handler_for_operation(self, operation, col):
        """
        Returns the appropriate handler for the given operation.
        """
        if operation in SyncCollectionHandler.operations:
            if not self.collection_handler:
                self.collection_handler = SyncCollectionHandler(col, self)
            return self.collection_handler
        elif operation in ["begin", "mediaChanges", "mediaSanity", "uploadChanges", "downloadFiles"]:
            if not self.media_handler:
                # Initialize modern media manager with the user's directory path
                # self.path is already the user directory (e.g., ./collections/users/test)
                user_folder = self.path
                self.media_manager = ServerMediaManager(user_folder)
                self.media_handler = MediaSyncHandler(self.media_manager, self)
            return self.media_handler
        else:
            raise ValueError("Operation '%s' is not supported." % operation)


# Modern sync request class
class SyncRequest:
    """Modern request parser for Anki sync protocol."""
    
    def __init__(self, environ):
        self.environ = environ
        self.path = environ["PATH_INFO"]
        self.method = environ["REQUEST_METHOD"]
        self._data = None
        self._sync_header = None
        
    def get_sync_header(self):
        """Parse the anki-sync header."""
        if self._sync_header is None:
            header_value = self.environ.get("HTTP_ANKI_SYNC", "")
            if header_value:
                try:
                    self._sync_header = json.loads(header_value)
                except json.JSONDecodeError:
                    self._sync_header = {}
            else:
                self._sync_header = {}
        return self._sync_header
    
    def get_body_data(self):
        """Get and decompress the request body without blocking when CONTENT_LENGTH is absent."""
        if self._data is not None:
            return self._data
            
        content_length_str = self.environ.get("CONTENT_LENGTH")
        logger.info(f"Raw CONTENT_LENGTH header: '{content_length_str}'")
        if not content_length_str:  # Handles None or empty string
            content_length = 0
        else:
            try:
                content_length = int(content_length_str)
            except ValueError:
                logger.warning(f"Malformed CONTENT_LENGTH header: '{content_length_str}'. Assuming 0.")
                content_length = 0

        logger.info(f"Parsed content_length: {content_length}")

        transfer_encoding = self.environ.get('HTTP_TRANSFER_ENCODING', '').lower()
        logger.info(f"Transfer-Encoding header: '{transfer_encoding}'")

        # If chunked transfer encoding, manually decode the chunks (wsgiref lacks support)
        if content_length == 0 and 'chunked' in transfer_encoding:
            logger.info("Handling chunked request body manually")
            raw_chunks = b''
            inp = self.environ['wsgi.input']
            while True:
                # Read chunk size line
                size_line = inp.readline()
                if not size_line:
                    break  # EOF
                size_line = size_line.strip()
                try:
                    chunk_size = int(size_line, 16)
                except ValueError:
                    logger.warning(f"Malformed chunk size: {size_line}")
                    break
                if chunk_size == 0:
                    # Discard trailing CRLF after last chunk
                    inp.readline()
                    break
                chunk = inp.read(chunk_size)
                raw_chunks += chunk
                # Discard trailing CRLF
                inp.read(2)
            raw_data = raw_chunks
        elif content_length == 0:
            logger.info("CONTENT_LENGTH is 0/absent – treating request body as empty to avoid blocking (non-chunked).")
            raw_data = b""
        else:
            raw_data = self.environ["wsgi.input"].read(content_length)
        
        if not raw_data:
            logger.info("Request body is empty – treating as empty JSON.")
            self._data = b"{}"
            return self._data

        # Try multiple decompression methods
        try:
            # Try zstd decompression first (modern Anki)
            dctx = zstd.ZstdDecompressor()
            self._data = dctx.decompress(raw_data)
            logger.info(f"Successfully zstd-decompressed payload. Length: {len(self._data)}")
        except zstd.ZstdError as e:
            logger.warning(f"Zstd decompression failed: {e}")
            # Try streaming decompression for cases where content size isn't in header
            try:
                dctx = zstd.ZstdDecompressor()
                with dctx.stream_reader(io.BytesIO(raw_data)) as reader:
                    self._data = reader.read()
                logger.info(f"Successfully zstd stream-decompressed payload. Length: {len(self._data)}")
            except Exception as e2:
                logger.warning(f"Zstd stream decompression also failed: {e2}. Falling back to legacy parsing.")
                if raw_data.startswith(b'{'):
                    logger.info("Treating as plain JSON since it starts with '{'")
                    self._data = raw_data
                else:
                    logger.info("Attempting legacy form data parsing")
                    self._data = self._parse_legacy_form_data(raw_data)
        
        return self._data
    
    def _parse_legacy_form_data(self, raw_data):
        """Parse legacy multipart form data format."""
        try:
            data_str = raw_data.decode('utf-8', errors='ignore')
            # Simplified regex, focusing on the name="u" and name="p" parts and the value after newlines
            u_match = re.search(r'name="u".*?\r?\n\r?\n(.*?)\r?\n', data_str, re.IGNORECASE | re.DOTALL)
            p_match = re.search(r'name="p".*?\r?\n\r?\n(.*?)\r?\n', data_str, re.IGNORECASE | re.DOTALL)
            
            if u_match and p_match:
                result = {
                    "u": u_match.group(1).strip(),
                    "p": p_match.group(1).strip()
                }
                logger.info(f"Legacy form data parsed (multipart): u='{result['u']}', p='****'")
                return json.dumps(result).encode('utf-8')

            # Fallback #2: application/x-www-form-urlencoded style 'u=..&p=..'
            from urllib.parse import parse_qs
            qs = parse_qs(data_str)
            if 'u' in qs and 'p' in qs:
                result = {"u": qs['u'][0], "p": qs['p'][0]}
                logger.info(f"Legacy form data parsed (urlencoded): u='{result['u']}', p='****'")
                return json.dumps(result).encode('utf-8')

            # Log preview for debugging
            logger.debug(f"Legacy parse failed. Raw data preview: {data_str[:150]}")
        except Exception as e:
            logger.error(f"Legacy form data parsing exception: {e}")
        
        logger.warning("Fallback: _parse_legacy_form_data returning empty JSON.")
        return b"{}"
    
    def get_json_data(self):
        """Get parsed JSON data from the request body."""
        data_bytes = self.get_body_data()
        if not data_bytes:
            return {}
        try:
            # Attempt to decode as UTF-8. If this fails, log and return empty.
            decoded_str = data_bytes.decode('utf-8')
        except UnicodeDecodeError as e:
            logger.error(f"UTF-8 decoding failed for JSON parsing: {e}. Data (first 100 bytes): {data_bytes[:100]}")
            return {}

        try:
            # Attempt to parse JSON. If this fails, log and return empty.
            parsed_json = json.loads(decoded_str)
            logger.info("Successfully parsed JSON from request body.")
            return parsed_json
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing failed: {e}. Decoded string (first 100 chars): {decoded_str[:100]}")
            return {}
    
    def get_sync_key(self):
        """Get the sync key from header or data."""
        header = self.get_sync_header()
        if header.get('k'):
            return header['k']
            
        # Fallback to JSON data
        data = self.get_json_data()
        return data.get('k', '')
    
    def get_session_key(self):
        """Get the session key from header or data."""
        header = self.get_sync_header()
        if header.get('s'):
            return header['s']
            
        # Fallback to JSON data  
        data = self.get_json_data()
        return data.get('sk', '')
    
    def get_sync_version(self):
        """Get the sync version from header."""
        header = self.get_sync_header()
        return header.get('v', SYNC_VERSION_MIN)
    
    def get_client_version(self):
        """Get the client version from header."""
        header = self.get_sync_header()
        return header.get('c', '')


class chunked(object):
    """decorator"""

    def __init__(self, func):
        wraps(func)(self)

    def __call__(self, *args, **kwargs):
        clss = args[0]
        environ = args[1]
        start_response = args[2]
        b = SyncRequest(environ)
        args = (
            clss,
            b,
        )
        try:
            w = self.__wrapped__(*args, **kwargs)

            # NEW: allow handler to return (body, original_size)
            if isinstance(w, tuple) and len(w) == 2:
                body, orig = w
                resp = Response(body, content_type='application/octet-stream')
                resp.headers['anki-original-size'] = str(orig)
                resp.headers['Content-Length'] = str(len(body)) # Explicitly set Content-Length
                logger.info(f"Setting anki-original-size header: {orig} bytes for path {environ.get('PATH_INFO')}")
            else:
                # w could be raw bytes or a Response object
                if isinstance(w, (bytes, bytearray)):
                    resp = Response(w, content_type='application/octet-stream')
                    resp.headers['anki-original-size'] = str(len(w))
                    resp.headers['Content-Length'] = str(len(w)) # Explicitly set Content-Length
                    logger.info(f"Auto-added anki-original-size header: {len(w)} bytes for path {environ.get('PATH_INFO')}")
                else:
                    resp = Response(w)

            return resp(environ, start_response)
        except HTTPBadRequest as e:
            resp = Response(str(e), status=400)
            return resp(environ, start_response)
        except HTTPUnauthorized as e:
            resp = Response(str(e), status=401)
            return resp(environ, start_response)
        except HTTPForbidden as e:
            resp = Response(str(e), status=403)
            return resp(environ, start_response)
        except HTTPNotFound as e:
            resp = Response(str(e), status=404)
            return resp(environ, start_response)
        except HTTPInternalServerError as e:
            resp = Response(str(e), status=500)
            return resp(environ, start_response)
        except Exception as e:
            logger.exception("Unhandled exception in sync operation")
            resp = Response(str(e), status=500)
            return resp(environ, start_response)

    def __get__(self, instance, cls):
        if instance is None:
            return self
        else:
            return types.MethodType(self, instance)


class SyncApp:
    valid_urls = (
        SyncCollectionHandler.operations
        + ["hostKey", "upload", "download"]
        + ["begin", "mediaChanges", "mediaSanity", "uploadChanges", "downloadFiles"]  # Media sync endpoints
        + ["provision-user"]  # User provisioning endpoint
    )

    def __init__(self, config):
        self.config = config
        self.user_manager = get_user_manager(config)
        self.session_manager = get_session_manager(config)  # Use persistent session manager
        
        # Inject user_manager into session_manager for token refresh integration
        if hasattr(self.session_manager, '__dict__'):
            self.session_manager.user_manager = self.user_manager
        
        # Initialize collection manager and other required attributes
        from ankisyncd.collection import CollectionManager
        self.collection_manager = CollectionManager(config)
        self.setup_new_collection = None  # Can be set if needed
        
        # Set up data root and other paths
        self.data_root = config.get('data_root', '/tmp/ankisyncd')
        os.makedirs(self.data_root, exist_ok=True)

    def session_factory(self, username, path):
        """Factory function to create sessions as expected by session manager."""
        return SyncUserSession(
            username,
            path,
            self.collection_manager,
            setup_new_collection=self.setup_new_collection,
        )

    def generateHostKey(self, username):
        """
        Generates a host key for the given user. This key is used to authenticate
        the user session.
        """
        import hashlib

        return hashlib.md5((username + str(time.time())).encode("utf-8")).hexdigest()

    def create_session(self, username, user_path):
        """
        Creates a new session for the given user.
        """
        return SyncUserSession(
            username,
            user_path,
            self.collection_manager,
            setup_new_collection=self.setup_new_collection,
        )

    def _decode_data(self, data, compression=0):
        if compression:
            data = gzip.decompress(data)
        return data

    def operation_hostKey(self, username, password):
        """
        Handles the hostKey operation for user authentication.
        """
        from ankisyncd.exceptions import (
            CognitoInvalidCredentialsException,
            CognitoUserNotConfirmedException,
            CognitoPasswordResetRequiredException,
            CognitoPasswordChangeRequiredException
        )
        
        try:
            if self.user_manager.authenticate(username, password):
                hkey = self.generateHostKey(username)
                user_dir = self.user_manager.userdir(username)
                user_path = os.path.join(self.user_manager.collection_path, user_dir)
                session = self.create_session(username, user_path)
                self.session_manager.save(hkey, session)
                return {"key": hkey}
            else:
                # Traditional authentication failure (for SQLite or simple managers)
                return {"error": "auth"}
                
        except CognitoInvalidCredentialsException:
            # Map NotAuthorizedException, UserNotFoundException, InvalidParameterException, TooManyRequestsException
            # → return {"error": "auth"} (client shows "login failed")
            return {"error": "auth"}
            
        except CognitoUserNotConfirmedException:
            # Map UserNotConfirmedException
            # → return {"error": "account-unconfirmed"}
            return {"error": "account-unconfirmed"}
            
        except (CognitoPasswordResetRequiredException, CognitoPasswordChangeRequiredException):
            # Map PasswordResetRequiredException | PasswordChangeRequiredException
            # → return {"error": "password-change-required"}
            return {"error": "password-change-required"}

    def operation_upload(self, col, data, session):
        # Verify integrity of the received database file before replacing our
        # existing db.
        temp_db_path = session.get_collection_path() + ".tmp"
        with open(temp_db_path, "wb") as f:
            f.write(data)

        # TODO: Verify the database integrity, and only then replace the original.
        
        # Close the current collection before replacing the file
        if hasattr(col, 'close'):
            col.close()
        
        # Replace the collection file
        os.rename(temp_db_path, session.get_collection_path())
        
        # Force the collection manager to reload the collection from the new file
        # by closing the cached collection wrapper
        if hasattr(session, 'collection_manager'):
            col_path = session.get_collection_path()
            if col_path in session.collection_manager.collections:
                session.collection_manager.collections[col_path].close()
                del session.collection_manager.collections[col_path]

    def operation_download(self, col, session):
        # returns user data (not media) as a sqlite3 database for replacing their
        # local copy in Anki
        return open(session.get_collection_path(), "rb").read()
    
    def operation_queue_status(self, session):
        """
        Returns the current sync queue status for debugging purposes.
        This is not part of the standard Anki sync protocol.
        """
        user_sync_queue = get_user_sync_queue()
        username = session.name
        status = user_sync_queue.get_queue_status(username)
        return json.dumps(status)

    @chunked
    def __call__(self, req):
        # cgi file can only be read once,and will be blocked after being read once more
        # so i call SyncRequest.parse only once,and bind its return result to properties
        # POST and params (set return result as property values)
        
        # Log sync attempt start
        sync_start_time = time.time()
        client_ip = req.environ.get('REMOTE_ADDR', 'unknown')
        user_agent = req.environ.get('HTTP_USER_AGENT', 'unknown')
        
        try:
            if req.path.startswith("/msync/"):
                # Media sync endpoint
                result = self._handle_media_sync(req)
                operation = req.path.split('/')[-1] if '/' in req.path else 'unknown'
                logger.info(f"✅ MEDIA SYNC SUCCESS: {operation} from {client_ip} in {time.time() - sync_start_time:.2f}s")
                return result
            elif req.path.startswith("/sync/"):
                # Collection sync endpoint
                result = self._handle_collection_sync(req)
                operation = req.path.split('/')[-1] if '/' in req.path else 'unknown'
                logger.info(f"✅ COLLECTION SYNC SUCCESS: {operation} from {client_ip} in {time.time() - sync_start_time:.2f}s")
                return result
            elif req.path == "/provision-user":
                # User provisioning endpoint for Cognito triggers
                result = self._handle_user_provisioning(req)
                logger.info(f"✅ USER PROVISIONING SUCCESS from {client_ip} in {time.time() - sync_start_time:.2f}s")
                return result
            else:
                logger.warning(f"❌ SYNC FAILED: Invalid endpoint {req.path} from {client_ip}")
                raise HTTPBadRequest("Invalid sync endpoint")
                
        except Exception as e:
            operation = req.path.split('/')[-1] if '/' in req.path else 'unknown'
            logger.warning(f"❌ SYNC FAILED: {operation} from {client_ip} - {type(e).__name__}: {str(e)}")
            raise

    def _handle_media_sync(self, req):
        """Handle media sync endpoints (/msync/)."""
        # Extract operation from path
        path_parts = req.path.strip("/").split("/")
        if len(path_parts) < 2:
            raise HTTPBadRequest("Invalid media sync path")
        
        operation = path_parts[1]  # e.g., "begin", "mediaChanges", etc.
        
        if operation not in ["begin", "mediaChanges", "mediaSanity", "uploadChanges", "downloadFiles"]:
            raise HTTPBadRequest(f"Unknown media sync operation: {operation}")

        # Get host key from request - media sync uses host key (k) for all operations
        # Based on Anki reference: media sync always uses the host key, not session key
        session_key = None
        
        # First try to get from anki-sync header (modern clients)
        sync_header = req.get_sync_header()
        if sync_header and 'k' in sync_header:
            session_key = sync_header['k']
        
        # Fallback to query params or POST data for legacy clients
        if not session_key:
            if hasattr(req, 'params') and 'k' in req.params:
                session_key = req.params['k']
            elif hasattr(req, 'params') and 'sk' in req.params:
                session_key = req.params['sk']
            else:
                # Try to get from POST data
                try:
                    post_data = req.get_json_data()
                    session_key = post_data.get('k') or post_data.get('sk')
                except:
                    pass
        
        if not session_key:
            raise HTTPBadRequest("Missing session key")

        session = self.session_manager.load(session_key, self.session_factory)
        if not session:
            raise HTTPForbidden("Invalid session")
        
        # For media sync, we don't need a collection object
        handler = session.get_handler_for_operation(operation, None)
        
        # Handle the specific operation
        if operation == "begin":
            # Extract client version
            client_version = ""
            if hasattr(req, 'params') and 'v' in req.params:
                client_version = req.params['v']
            else:
                try:
                    post_data = req.get_json_data()
                    client_version = post_data.get('v', '')
                except:
                    pass
            
            # Pass the session key to begin method so it can return it in 'sk' field
            result = handler.begin(client_version, session_key)
            
        elif operation == "mediaChanges":
            try:
                # Get the raw body data (already decompressed by get_body_data)
                body_data = req.get_body_data()
                
                # Parse request (data is already decompressed)
                request_data = json.loads(body_data.decode('utf-8'))
                last_usn = request_data.get('lastUsn', 0)
                logger.info(f"mediaChanges request: last_usn={last_usn}")
            except Exception as e:
                logger.error(f"Error parsing mediaChanges request: {e}")
                last_usn = 0
            
            result = handler.media_changes(last_usn)
            
        elif operation == "uploadChanges":
            # Raw binary data for zip file - don't try to parse as JSON
            # Get the raw body data directly
            zip_data = req.get_body_data()
            result = handler.upload_changes(zip_data)
            
        elif operation == "downloadFiles":
            try:
                # Get the raw body data (already decompressed by get_body_data)
                body_data = req.get_body_data()
                
                # Parse request (data is already decompressed)
                request_data = json.loads(body_data.decode('utf-8'))
                logger.info(f"downloadFiles request data: {request_data}")
                
                files = request_data.get("files", [])
                logger.info(f"downloadFiles requesting {len(files)} files: {files}")
                
                result = handler.download_files(files)
            except Exception as e:
                logger.error(f"Error processing downloadFiles request: {e}")
                result = handler.download_files([])
            
            # Return raw zip data with original size for chunked decorator
            return (result, len(result))
            
        elif operation == "mediaSanity":
            try:
                # Get the raw body data (already decompressed by get_body_data)
                body_data = req.get_body_data()
                
                # Parse request (data is already decompressed)
                request_data = json.loads(body_data.decode('utf-8'))
                local_count = request_data.get('local', 0)
                logger.info(f"mediaSanity request: local_count={local_count}")
            except Exception as e:
                logger.error(f"Error parsing mediaSanity request: {e}")
                local_count = 0
            
            result = handler.media_sanity(local_count)

        # Build response payload and ensure anki-original-size header is included
        if operation == "downloadFiles":
            # Binary zip data - don't double-compress, but still include size header
            payload = result if isinstance(result, (bytes, bytearray)) else bytes(result)
            return payload, len(payload)

        # For JSON responses, compress with zstd to match modern Anki expectations
        # and return (compressed, original_size)
        json_payload = json.dumps(result).encode("utf-8")
        orig_size = len(json_payload)
        compressed = zstd.ZstdCompressor().compress(json_payload)
        return compressed, orig_size

    def _handle_collection_sync(self, req):
        """Handle collection sync endpoints (/sync/)."""
        # Debug: log complete request information
        logger.info(f"=== INCOMING REQUEST ===")
        logger.info(f"Path: {req.path}")
        logger.info(f"Method: {req.method}")
        logger.info(f"User-Agent: {req.environ.get('HTTP_USER_AGENT', 'None')}")
        logger.info(f"Content-Type: {req.environ.get('CONTENT_TYPE', 'None')}")
        logger.info(f"Content-Length: {req.environ.get('CONTENT_LENGTH', 'None')}")
        logger.info(f"Anki-Sync Header: {req.environ.get('HTTP_ANKI_SYNC', 'None')}")
        
        # Extract operation from path, handling both /sync/ and /sync/sync/ prefixes
        path_parts = req.path.strip("/").split("/")
        if len(path_parts) < 2:
            raise HTTPBadRequest("Invalid sync path")
        
        # Handle both /sync/hostKey and /sync/sync/hostKey paths
        operation = path_parts[-1] if path_parts[-1] in self.valid_urls else path_parts[-2]
        
        if operation not in self.valid_urls:
            raise HTTPBadRequest(f"Unknown operation: {operation}")

        logger.info(f"Operation: {operation}")

        # Handle authentication operations
        if operation == "hostKey":
            # Get username and password from JSON data
            data = req.get_json_data()
            sync_header = req.get_sync_header()
            
            logger.info(f"Request body data: {data}")
            logger.info(f"Sync header: {sync_header}")
            
            # Extract username/password from JSON data first
            username = (data.get('username') or 
                       data.get('u') or 
                       data.get('email'))
            password = data.get('password') or data.get('p')
            
            # If JSON did not provide credentials, try HTTP Basic Auth header
            if (not username or not password):
                auth_header = req.environ.get('HTTP_AUTHORIZATION', '')
                if auth_header.startswith('Basic '):
                    import base64
                    try:
                        decoded = base64.b64decode(auth_header[6:]).decode('utf-8')
                        if ':' in decoded:
                            username_hdr, password_hdr = decoded.split(':', 1)
                            # Only overwrite if values are missing
                            if not username:
                                username = username_hdr
                            if not password:
                                password = password_hdr
                    except Exception as e:
                        logger.warning(f"Failed to parse Basic Auth header: {e}")

            logger.info(f"Extracted credentials - identifier: '{username}', password present: {bool(password)}")
            
            # Check if this is a discovery request from modern client
            sync_header = req.get_sync_header()
            if not username and not password and sync_header.get("k") == "" and not data:
                # Discovery request - client should send credentials in body for login
                logger.info("Discovery request detected - expecting credentials in request body")
                logger.info("This means client needs to show login dialog and send username/password")
                # Raise HTTP 400 to signal client to prompt for auth (Anki expects this)
                raise HTTPBadRequest("expected auth")
            
            if not username or not password:
                logger.warning(f"Incomplete credentials - identifier: '{username}', password present: {bool(password)}")
                raise HTTPForbidden("Missing username or password")
            
            logger.info(f"Attempting authentication for user: '{username}'")
            result = self.operation_hostKey(username, password)
            logger.info(f"Authentication successful for user: '{username}', returning host key")
            
            # Return zstd-compressed JSON response with original size header
            payload = json.dumps(result).encode('utf-8')
            orig_size = len(payload)
            compressed = zstd.ZstdCompressor().compress(payload)
            return compressed, orig_size

        # For other operations, need session key
        session_key = req.get_sync_key() or req.get_session_key()
        
        session = self.session_manager.load(session_key, self.session_factory)
        if not session:
            raise HTTPForbidden("Invalid session")
        
        # Get collection
        col = self.collection_manager.get_collection(
            session.get_collection_path(), 
            session.setup_new_collection
        )
        
        # Handle upload/download operations (these might use different data format)
        if operation == "upload":
            # Collection uploads are often sent with chunked transfer encoding.
            # Rely on SyncRequest.get_body_data() which already handles both
            # Content-Length and manual chunk decoding + zstd decompression.
            raw_payload = req.get_body_data()
            logger.info(f"Upload received raw payload of {len(raw_payload)} bytes (post-dechunk/decompress)")

            # The body sent by modern Anki clients is a zstd-compressed SQLite
            # file.  If get_body_data() could not decompress (e.g. legacy
            # gzip or no compression), attempt fallback decompression below.
            data = raw_payload
            if not data.startswith(b'SQLite format 3'):
                try:
                    data = gzip.decompress(raw_payload)
                    logger.info(f"Upload gzip-decompressed to {len(data)} bytes")
                except Exception:
                    pass  # leave as-is; may already be uncompressed
            
            # Verify it looks like a SQLite database
            if data.startswith(b'SQLite format 3'):
                logger.info("Upload data confirmed as SQLite database")
            else:
                logger.warning(f"Upload data doesn't appear to be SQLite: {data[:20]}")
            
            self.operation_upload(col, data, session)
            
            # Return zstd-compressed response for modern clients with original size
            payload = b"OK"
            orig_size = len(payload)
            compressed = zstd.ZstdCompressor().compress(payload)
            return compressed, orig_size
            
        elif operation == "download":
            result = self.operation_download(col, session)
            # Compress the response with original size
            orig_size = len(result)
            compressed = zstd.ZstdCompressor().compress(result)
            return compressed, orig_size
        
        # Handle other sync operations with modern protocol support
        handler = session.get_handler_for_operation(operation, col)
        
        # Parse request data from JSON
        request_data = req.get_json_data()
        
        # Map sync protocol parameters to handler method parameters
        sync_version = req.get_sync_version()
        client_version = req.get_client_version()
        
        # For meta operation, map to expected parameter names
        if operation == "meta":
            request_data['v'] = sync_version
            request_data['cv'] = client_version
            # Remove any internal parameters that shouldn't be passed to handler
            request_data.pop('_sync_version', None)
            request_data.pop('_client_version', None)
        else:
            # For other operations, don't add internal parameters that handlers don't expect
            # The handlers already have access to sync version and client version if needed
            pass
        
        # Filter out internal parameters that modern clients send but handlers don't expect
        internal_params = ['_pad', '_sync_version', '_client_version']
        for param in internal_params:
            request_data.pop(param, None)
        
        # Execute the operation in a thread
        result = self._execute_handler_method_in_thread(
            operation, 
            request_data, 
            session
        )
        
        # Return zstd-compressed JSON response with original size
        payload = json.dumps(result).encode('utf-8')
        orig_size = len(payload)
        compressed = zstd.ZstdCompressor().compress(payload)
        return compressed, orig_size

    @staticmethod
    def _execute_handler_method_in_thread(method_name, keyword_args, session):
        """
        Gets and runs the handler method specified by method_name inside the
        thread for session. The handler method will access the collection as
        self.col.
        
        This method now uses per-user sync queuing to ensure only one sync
        operation per user can run at a time.
        """

        def sync_operation():
            """The actual sync operation that will be queued per-user."""
            # Get collection wrapper first
            col_wrapper = session.collection_manager.get_collection(
                session.get_collection_path(), 
                session.setup_new_collection
            )

            def run_func_with_wrapper(col):
                """Function that runs inside the wrapper's execute method with actual collection."""
                # Get handler with the actual collection object
                handler = session.get_handler_for_operation(method_name, col)
                
                # Update the handler's collection reference to use the actual collection
                # instead of the wrapper it was originally initialized with
                original_col = handler.col
                handler.col = col
                
                try:
                    handler_method = getattr(handler, method_name)
                    res = handler_method(**keyword_args)
                    # col.save() is deprecated - saving is automatic in modern Anki
                    
                    # Force WAL checkpoint to commit changes to main database file
                    try:
                        if hasattr(col, '_db') and col._db:
                            col._db.execute("PRAGMA wal_checkpoint(FULL)")
                            col._db.commit()
                    except Exception as e:
                        # Log but don't fail if checkpoint fails
                        import logging
                        logging.warning(f"WAL checkpoint failed: {e}")
                    
                    return res
                finally:
                    # Restore the original collection reference
                    handler.col = original_col

            run_func_with_wrapper.__name__ = method_name  # More useful debugging messages.

            # Use the wrapper's execute method to run with the actual collection
            result = col_wrapper.execute(run_func_with_wrapper, waitForReturn=True)
            return result

        # Use the user sync queue to ensure only one sync per user at a time
        user_sync_queue = get_user_sync_queue()
        username = session.name
        
        try:
            result = user_sync_queue.execute_sync_operation(username, sync_operation)
            return result
        except Exception as e:
            logging.error(f"Sync operation failed for user {username}: {e}")
            raise

    def _handle_user_provisioning(self, req):
        """Handle user provisioning requests from Cognito triggers."""
        if req.method != 'POST':
            raise HTTPBadRequest("User provisioning requires POST method")
        
        # Check for API key authentication
        api_key = req.headers.get('X-API-Key') or self.config.get('provision_api_key')
        if not api_key:
            raise HTTPUnauthorized("API key required for user provisioning")
        
        # Verify API key
        expected_api_key = self.config.get('provision_api_key')
        if not expected_api_key or api_key != expected_api_key:
            raise HTTPUnauthorized("Invalid API key")
        
        try:
            # Parse JSON request data
            request_data = req.get_json_data()
            if not request_data:
                raise HTTPBadRequest("JSON request body required")
            
            username = request_data.get('username')
            email = request_data.get('email')
            cognito_user_id = request_data.get('cognito_user_id')
            
            if not username:
                raise HTTPBadRequest("Username is required")
            
            # Use username as the primary identifier for folder naming
            user_identifier = username
            
            logger.info(f"Provisioning user: {user_identifier} (Cognito ID: {cognito_user_id})")
            
            # Add user to auth database for compatibility/tracking
            # Note: Collection directory will be created on first sync attempt
            # Add user to SQLite auth database for compatibility (optional)
            # This allows the system to track provisioned users even when using Cognito auth
            auth_db_updated = False
            try:
                from ankisyncd.users.sqlite_manager import SqliteUserManager
                # Check if we have a SQLite auth database configured (fallback auth)
                auth_db_path = self.config.get('auth_db_path')
                if auth_db_path:
                    # Create a temporary SQLite manager to add the user
                    sqlite_manager = SqliteUserManager(auth_db_path, self.user_manager.collection_path)
                    
                    # Add user with a placeholder password since Cognito handles auth
                    placeholder_password = "cognito_user"  # Not used for actual auth
                    if not sqlite_manager.user_exists(user_identifier):
                        sqlite_manager.add_user(user_identifier, placeholder_password)
                        logger.info(f"Added user '{user_identifier}' to SQLite auth database")
                        auth_db_updated = True
                    else:
                        logger.info(f"User '{user_identifier}' already exists in SQLite auth database")
                        auth_db_updated = True
                else:
                    logger.info("No SQLite auth database configured - skipping auth DB update")
                    
            except Exception as e:
                logger.warning(f"Failed to add user to SQLite auth database: {e}")
                # Don't fail the provisioning if SQLite update fails
            
            # Return success response
            response_data = {
                'success': True,
                'message': f'User {user_identifier} provisioned successfully',
                'auth_db_updated': auth_db_updated,
                'username': user_identifier,
                'note': 'Collection directory will be created on first sync attempt'
            }
            
            return Response(
                json.dumps(response_data),
                content_type='application/json',
                status=200
            )
            
        except HTTPException:
            # Re-raise HTTP exceptions
            raise
        except Exception as e:
            logger.error(f"Error provisioning user: {str(e)}")
            raise HTTPInternalServerError(f"Failed to provision user: {str(e)}")


class SimpleThreadExecutor:
    """Simple thread executor for compatibility with the original sync code."""
    
    def execute(self, func, args=None, kw=None):
        """Execute a function with the given arguments."""
        args = args or []
        kw = kw or {}
        
        # Execute the function directly with provided arguments
        return func(*args, **kw)


def make_app(global_conf, **local_conf):
    return SyncApp(**local_conf)
