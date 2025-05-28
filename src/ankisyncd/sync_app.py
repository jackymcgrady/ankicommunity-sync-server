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
from webob import Response
from webob.exc import *
import urllib.parse
from functools import wraps
import anki
import anki.db
import anki.utils
from anki.utils import intTime, ids2str
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

        # Make sure the media database is open!
        self.col.media.connect()
        
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
                    schema_change = anki.utils.intTime(1000)
            else:
                collection_bytes = 0
        except Exception:
            collection_bytes = 0

        # Build modern meta response
        meta_response = {
            "mod": collection_change,
            "scm": schema_change,
            "usn": self.col.usn(),
            "ts": anki.utils.intTime(),
            "musn": self.col.media.lastUsn(),
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
        return super().finish(anki.utils.intTime(1000))

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
                # Initialize modern media manager
                user_folder = os.path.dirname(self.path)
                self.media_manager = ServerMediaManager(user_folder)
                self.media_handler = MediaSyncHandler(self.media_manager, self)
            return self.media_handler
        else:
            raise ValueError("Operation '%s' is not supported." % operation)


class Requests(object):
    def __init__(self, environ: dict):
        self.environ = environ

    @property
    def params(self):
        return self.request_items_dict

    @params.setter
    def params(self, value):
        """
        A dictionary-like object containing both the parameters from
        the query string and request body.
        """
        self.request_items_dict = value

    @property
    def path(self) -> str:
        return self.environ["PATH_INFO"]

    @property
    def POST(self):
        return self._request_items_dict

    @POST.setter
    def POST(self, value):
        self._request_items_dict = value

    @property
    def parse(self):
        """Return a MultiDict containing all the variables from a form
        request.\n
        include not only post req,but also get"""
        env = self.environ
        query_string = env["QUERY_STRING"]
        content_len = env.get("CONTENT_LENGTH", "0")
        input = env.get("wsgi.input")
        length = 0 if content_len == "" else int(content_len)
        body = b""
        request_items_dict = {}
        if length == 0:
            if input is None:
                return request_items_dict
            if env.get("HTTP_TRANSFER_ENCODING", "0") == "chunked":
                # readlines and read(no argument) will block
                # convert byte str to number base 16
                leng = int(input.readline(), 16)
                c = 0
                bdry = b""
                data = []
                data_other = []
                while leng > 0:
                    c += 1
                    dt = input.read(leng + 2)
                    if c == 1:
                        bdry = dt
                    elif c >= 3:
                        # data
                        data_other.append(dt)
                    leng = int(input.readline(), 16)
                data_other = [item for item in data_other if item != b"\r\n\r\n"]
                for item in data_other:
                    if bdry in item:
                        break
                    # only strip \r\n if there are extra \n
                    # eg b'?V\xc1\x8f>\xf9\xb1\n\r\n'
                    data.append(item[:-2])
                request_items_dict["data"] = b"".join(data)
                others = data_other[len(data) :]
                boundary = others[0]
                others = b"".join(others).split(boundary.strip())
                others.pop()
                others.pop(0)
                for i in others:
                    i = i.splitlines()
                    key = re.findall(b'name="(.*?)"', i[2], flags=re.M)[0].decode(
                        "utf-8"
                    )
                    v = i[-1].decode("utf-8")
                    request_items_dict[key] = v
                return request_items_dict

            if query_string != "":
                # GET method
                body = query_string
                request_items_dict = urllib.parse.parse_qs(body)
                for k, v in request_items_dict.items():
                    request_items_dict[k] = "".join(v)
                return request_items_dict

        else:
            body = env["wsgi.input"].read(length)

        if body is None or body == b"":
            return request_items_dict
            # process body to dict
        repeat = body.splitlines()[0]
        items = re.split(repeat, body)
        # del first ,last item
        items.pop()
        items.pop(0)
        for item in items:
            if b'name="data"' in item:
                data_field = None
                # remove \r\n
                if b"application/octet-stream" in item:
                    # Ankidroid case
                    item = re.sub(
                        b'Content-Disposition: form-data; name="data"; filename="data"',
                        b"",
                        item,
                    )
                    item = re.sub(b"Content-Type: application/octet-stream", b"", item)
                    data_field = item.strip()
                else:
                    # PKzip file stream and others
                    item = re.sub(
                        b'Content-Disposition: form-data; name="data"; filename="data"',
                        b"",
                        item,
                    )
                    data_field = item.strip()
                request_items_dict["data"] = data_field
                continue
            item = re.sub(b"\r\n", b"", item, flags=re.MULTILINE)
            key = re.findall(b'name="(.*?)"', item)[0].decode("utf-8")
            v = item[item.rfind(b'"') + 1 :].decode("utf-8")
            request_items_dict[key] = v
        return request_items_dict


class chunked(object):
    """decorator"""

    def __init__(self, func):
        wraps(func)(self)

    def __call__(self, *args, **kwargs):
        clss = args[0]
        environ = args[1]
        start_response = args[2]
        b = Requests(environ)
        args = (
            clss,
            b,
        )
        w = self.__wrapped__(*args, **kwargs)
        resp = Response(w)
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
    )

    def __init__(self, config):
        self.config = config
        self.user_manager = get_user_manager(config)
        self.sessions = {}  # Session storage
        
        # Initialize collection manager and other required attributes
        from ankisyncd.collection import CollectionManager
        self.collection_manager = CollectionManager()
        self.setup_new_collection = None  # Can be set if needed
        
        # Set up data root and other paths
        self.data_root = config.get('data_root', '/tmp/ankisyncd')
        os.makedirs(self.data_root, exist_ok=True)

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
        if self.user_manager.authenticate(username, password):
            hkey = self.generateHostKey(username)
            user_path = self.user_manager.user_path(username)
            session = self.create_session(username, user_path)
            self.sessions[hkey] = session
            return {"key": hkey}
        else:
            raise HTTPForbidden()

    def operation_upload(self, col, data, session):
        # Verify integrity of the received database file before replacing our
        # existing db.
        temp_db_path = session.get_collection_path() + ".tmp"
        with open(temp_db_path, "wb") as f:
            f.write(data)

        # TODO: Verify the database integrity, and only then replace the original.

        os.rename(temp_db_path, session.get_collection_path())

    def operation_download(self, col, session):
        # returns user data (not media) as a sqlite3 database for replacing their
        # local copy in Anki
        return open(session.get_collection_path(), "rb").read()

    @chunked
    def __call__(self, req):
        # cgi file can only be read once,and will be blocked after being read once more
        # so i call Requests.parse only once,and bind its return result to properties
        # POST and params (set return result as property values)
        req.parse
        try:
            if req.path.startswith("/msync/"):
                # Media sync endpoint
                return self._handle_media_sync(req)
            elif req.path.startswith("/sync/"):
                # Collection sync endpoint
                return self._handle_collection_sync(req)
            else:
                raise HTTPBadRequest("Invalid sync endpoint")
        except Exception as e:
            logger.exception("Error in sync operation")
            raise HTTPInternalServerError(str(e))

    def _handle_media_sync(self, req):
        """Handle media sync endpoints (/msync/)."""
        # Extract operation from path
        path_parts = req.path.strip("/").split("/")
        if len(path_parts) < 2:
            raise HTTPBadRequest("Invalid media sync path")
        
        operation = path_parts[1]  # e.g., "begin", "mediaChanges", etc.
        
        if operation not in ["begin", "mediaChanges", "mediaSanity", "uploadChanges", "downloadFiles"]:
            raise HTTPBadRequest(f"Unknown media sync operation: {operation}")

        # Get session key from request
        if operation == "begin":
            # For begin, session key might be in query params or POST data
            if hasattr(req, 'params') and 'k' in req.params:
                session_key = req.params['k']
            else:
                # Try to get from POST data
                try:
                    post_data = json.loads(req.POST.decode('utf-8'))
                    session_key = post_data.get('k')
                except:
                    raise HTTPBadRequest("Missing session key")
        else:
            # For other operations, get from POST data
            try:
                if hasattr(req, 'params') and 'sk' in req.params:
                    session_key = req.params['sk']
                else:
                    # Try POST data
                    post_data = json.loads(req.POST.decode('utf-8'))
                    session_key = post_data.get('sk', post_data.get('k'))
            except:
                raise HTTPBadRequest("Missing session key")

        if not session_key or session_key not in self.sessions:
            raise HTTPForbidden("Invalid session")

        session = self.sessions[session_key]
        
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
                    post_data = json.loads(req.POST.decode('utf-8'))
                    client_version = post_data.get('v', '')
                except:
                    pass
            
            result = handler.begin(client_version)
            
        elif operation == "mediaChanges":
            try:
                post_data = json.loads(req.POST.decode('utf-8'))
                last_usn = post_data.get('lastUsn', 0)
            except:
                last_usn = 0
            
            result = handler.media_changes(last_usn)
            
        elif operation == "uploadChanges":
            # Raw binary data for zip file
            zip_data = req.POST
            result = handler.upload_changes(zip_data)
            
        elif operation == "downloadFiles":
            try:
                post_data = json.loads(req.POST.decode('utf-8'))
                files = post_data.get('files', [])
            except:
                files = []
            
            # This returns raw zip data, not JSON
            return handler.download_files(files)
            
        elif operation == "mediaSanity":
            try:
                post_data = json.loads(req.POST.decode('utf-8'))
                local_count = post_data.get('local', 0)
            except:
                local_count = 0
            
            result = handler.media_sanity(local_count)

        # Return JSON response for most operations
        return json.dumps(result).encode('utf-8')

    def _handle_collection_sync(self, req):
        """Handle collection sync endpoints (/sync/)."""
        # Extract operation from path
        path_parts = req.path.strip("/").split("/")
        if len(path_parts) < 2:
            raise HTTPBadRequest("Invalid sync path")
        
        operation = path_parts[1]
        
        if operation not in self.valid_urls:
            raise HTTPBadRequest(f"Unknown operation: {operation}")

        # Handle authentication operations
        if operation == "hostKey":
            try:
                post_data = json.loads(req.POST.decode('utf-8'))
                username = post_data.get('u')
                password = post_data.get('p')
                if not username or not password:
                    raise HTTPBadRequest("Missing username or password")
                result = self.operation_hostKey(username, password)
                return json.dumps(result).encode('utf-8')
            except HTTPForbidden:
                raise
            except Exception as e:
                logger.error(f"Error in hostKey operation: {e}")
                raise HTTPBadRequest("Invalid authentication request")

        # For other operations, need session
        session_key = None
        if hasattr(req, 'params') and 'k' in req.params:
            session_key = req.params['k']
        
        if not session_key or session_key not in self.sessions:
            raise HTTPForbidden("Invalid session")

        session = self.sessions[session_key]
        
        # Get collection
        col = self.collection_manager.get_collection(
            session.get_collection_path(), 
            session.setup_new_collection
        )
        
        # Handle upload/download operations
        if operation == "upload":
            data = self._decode_data(req.POST, req.params.get('c', 0))
            self.operation_upload(col, data, session)
            return b"OK"
        elif operation == "download":
            return self.operation_download(col, session)
        
        # Handle other sync operations with modern protocol support
        handler = session.get_handler_for_operation(operation, col)
        
        # Parse request data
        try:
            request_data = json.loads(req.POST.decode('utf-8')) if req.POST else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            request_data = {}
        
        # Add sync version and client version to request context if available
        if hasattr(req, 'params'):
            if 'v' in req.params:
                try:
                    request_data['_sync_version'] = int(req.params['v'])
                except (ValueError, TypeError):
                    pass
            if 'cv' in req.params:
                request_data['_client_version'] = req.params['cv']
        
        # Execute the operation in a thread
        result = self._execute_handler_method_in_thread(
            operation, 
            request_data, 
            session
        )
        
        return json.dumps(result).encode('utf-8')

    @staticmethod
    def _execute_handler_method_in_thread(method_name, keyword_args, session):
        """
        Gets and runs the handler method specified by method_name inside the
        thread for session. The handler method will access the collection as
        self.col.
        """

        def run_func(col, **keyword_args):
            # Retrieve the correct handler method.
            handler = session.get_handler_for_operation(method_name, col)
            handler_method = getattr(handler, method_name)

            res = handler_method(**keyword_args)

            col.save()
            return res

        run_func.__name__ = method_name  # More useful debugging messages.

        # Send the closure to the thread for execution.
        thread = session.get_thread()
        result = thread.execute(run_func, kw=keyword_args)

        return result


class SimpleThreadExecutor:
    """Simple thread executor for compatibility with the original sync code."""
    
    def execute(self, func, args=None, kw=None):
        """Execute a function with the given arguments."""
        args = args or []
        kw = kw or {}
        
        # Get collection for the function
        if hasattr(func, '__self__') and hasattr(func.__self__, 'get_collection_path'):
            # This is a method call on a session
            session = func.__self__
            col_path = session.get_collection_path()
            col = session.collection_manager.get_collection(col_path, session.setup_new_collection)
            return func(col, *args, **kw)
        else:
            # Direct function call
            return func(*args, **kw)


def make_app(global_conf, **local_conf):
    return SyncApp(**local_conf)
