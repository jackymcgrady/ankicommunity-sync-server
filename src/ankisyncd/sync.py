# -*- coding: utf-8 -*-
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

# Taken from https://github.com/ankitects/anki/blob/cca3fcb2418880d0430a5c5c2e6b81ba260065b7/anki/sync.py

import io
import gzip
import random
import requests
import json
import os
import logging
import time
from typing import List, Tuple

from anki.db import DB, DBError
from anki.utils import checksum, dev_mode
from anki.consts import *
from anki.config import ConfigManager
from anki.utils import version_with_build
import anki
from anki.lang import ngettext

# Provide compatibility across Anki versions – see explanation in sync_app.py
from anki import utils as _anki_utils  # type: ignore

if hasattr(_anki_utils, "int_time"):
    int_time = _anki_utils.int_time  # pylint: disable=invalid-name
else:
    int_time = _anki_utils.intTime  # type: ignore[attr-defined]

ids2str = getattr(_anki_utils, "ids2str", getattr(_anki_utils, "ids2Str", None))

# `plat_desc` naming likewise changed in earlier versions.
plat_desc = getattr(_anki_utils, "plat_desc", getattr(_anki_utils, "platDesc", None))

__all__ = ["int_time", "ids2str", "plat_desc"]

from .schema_updater import SchemaUpdater

logger = logging.getLogger("ankisyncd.sync")

# Modern Anki sync protocol version constants
# Based on Anki reference: rslib/src/sync/version.rs
SYNC_VERSION_MIN = 8   # SYNC_VERSION_08_SESSIONKEY
SYNC_VERSION_MAX = 11  # SYNC_VERSION_11_DIRECT_POST

# Individual version constants for compatibility checks
SYNC_VERSION_08_SESSIONKEY = 8
SYNC_VERSION_09_V2_SCHEDULER = 9
SYNC_VERSION_10_V2_TIMEZONE = 10
SYNC_VERSION_11_DIRECT_POST = 11

# Legacy constant for backward compatibility
SYNC_VER = SYNC_VERSION_10_V2_TIMEZONE

# Sync transfer constants
# https://github.com/ankitects/anki/blob/cca3fcb2418880d0430a5c5c2e6b81ba260065b7/anki/consts.py#L50
SYNC_ZIP_SIZE = int(2.5 * 1024 * 1024)
# https://github.com/ankitects/anki/blob/cca3fcb2418880d0430a5c5c2e6b81ba260065b7/anki/consts.py#L51
SYNC_ZIP_COUNT = 25

def is_sync_version_supported(version: int) -> bool:
    """Check if the sync version is supported by this server."""
    return SYNC_VERSION_MIN <= version <= SYNC_VERSION_MAX

def is_multipart_version(version: int) -> bool:
    """Check if the sync version uses multipart requests (pre-v11)."""
    return version < SYNC_VERSION_11_DIRECT_POST

def is_zstd_version(version: int) -> bool:
    """Check if the sync version uses zstd compression (v11+)."""
    return version >= SYNC_VERSION_11_DIRECT_POST

def get_collection_schema_for_sync_version(version: int) -> int:
    """Get the appropriate collection schema version for the sync version."""
    if is_multipart_version(version):
        return 11  # SchemaVersion::V11
    else:
        return 18  # SchemaVersion::V18

# syncing vars
HTTP_TIMEOUT = 90
HTTP_PROXY = None
HTTP_BUF_SIZE = 64 * 1024

# Incremental syncing
##########################################################################


class Syncer(object):
    def __init__(self, col, server=None):
        self.col = col
        self.server = server
        # Initialize schema updater for dynamic field handling
        self.schema_updater = SchemaUpdater(col)
        
        # Set dynamic sync version based on schema
        self.sync_version = self.schema_updater.get_sync_version_for_schema()
        
        # Validate schema compatibility
        if not self.schema_updater.is_compatible_schema():
            raise Exception("Incompatible database schema detected. Please update Anki or check collection.")
        
        # Log schema information
        logger.info(f"Initialized Syncer with schema V{self.schema_updater.get_schema_version()}, sync version {self.sync_version}")
        
        # Check if data migration is needed
        if self.schema_updater.needs_data_migration():
            logger.warning("Data migration may be needed between JSON and table storage")

    # new added functions related to Syncer:
    #  these are removed from latest anki module
    ########################################################################
    def scm(self):
        """return schema"""
        scm = self.col.db.scalar("select scm from col")
        return scm

    def increment_usn(self):
        """usn+1 in db"""
        self.col.db.execute("update col set usn = usn + 1")

    def set_modified_time(self, now: int):
        self.col.db.execute("update col set mod=?", now)

    def set_last_sync(self, now: int):
        self.col.db.execute("update col set ls = ?", now)

    #########################################################################
    def meta(self):
        if self.col.schedVer() == 2 and self.sync_version < 9:
            return dict(
                scm=self.scm(),
                ts=int_time(),
                mod=self.col.mod,
                usn=self.col._usn,
                musn=0,
                msg="upgrade required",
                cont=False,
            )
        return dict(
            scm=self.scm(),
            ts=int_time(),
            mod=self.col.mod,
            usn=self.col._usn,
            musn=0,
            msg="",
            cont=True,
        )

    def changes(self):
        "Bundle up small objects."
        d = dict(models=self.getModels(), decks=self.getDecks(), tags=self.getTags())
        if self.lnewer:
            d["conf"] = self.col.all_config()
            d["crt"] = self.col.crt
        return d

    def mergeChanges(self, lchg, rchg):
        # then the other objects
        self.mergeModels(rchg["models"])
        self.mergeDecks(rchg["decks"])
        self.mergeTags(rchg["tags"])
        if "conf" in rchg:
            self.mergeConf(rchg["conf"])
        # this was left out of earlier betas
        if "crt" in rchg:
            self.col.crt = rchg["crt"]
        self.prepareToChunk()

    #     this fn was cloned from anki module(version 2.1.36)
    def basicCheck(self) -> bool:
        "Basic integrity check for syncing. True if ok."
        # cards without notes
        if self.col.db.scalar(
            """
select 1 from cards where nid not in (select id from notes) limit 1"""
        ):
            return False
        # notes without cards or models
        if self.col.db.scalar(
            """
select 1 from notes where id not in (select distinct nid from cards)
or mid not in %s limit 1"""
            % ids2str(self.col.models.ids())
        ):
            return False
        # invalid ords
        for m in self.col.models.all():
            # ignore clozes
            if m["type"] != MODEL_STD:
                continue
            if self.col.db.scalar(
                """
select 1 from cards where ord not in %s and nid in (
select id from notes where mid = ?) limit 1"""
                % ids2str([t["ord"] for t in m["tmpls"]]),
                m["id"],
            ):
                return False
        return True

    def sanityCheck(self):
        # Check only tables that exist in the current schema
        base_tables = ["cards", "notes", "revlog", "graves"]
        schema_specific_tables = []
        
        # Add schema-specific tables based on version
        if self.schema_updater.supports_table("deck_config"):
            schema_specific_tables.append("deck_config")
        if self.schema_updater.supports_table("tags"):
            schema_specific_tables.append("tags")
        if self.schema_updater.supports_table("notetypes"):
            schema_specific_tables.append("notetypes")
        if self.schema_updater.supports_table("decks"):
            schema_specific_tables.append("decks")
        
        tables = base_tables + schema_specific_tables
        
        for tb in tables:
            if self.schema_updater.supports_table(tb):
                try:
                    if self.col.db.scalar(f"select null from {tb} where usn=-1"):
                        return f"table had usn=-1: {tb}"
                except Exception as e:
                    logger.warning(f"Could not check table {tb}: {e}")
        
        self.col.sched.reset()

        # return summary of deck
        # make sched.counts() equal to default [0,0,0]
        # to make sure sync normally if sched.counts()
        # are not equal between different clients due to
        # different deck selection
        try:
            return [
                list([0, 0, 0]),
                self.col.db.scalar("select count() from cards"),
                self.col.db.scalar("select count() from notes"),
                self.col.db.scalar("select count() from revlog"),
                self.col.db.scalar("select count() from graves"),
                len(self.col.models.all()) if hasattr(self.col, 'models') else 0,
                len(self.col.decks.all()) if hasattr(self.col, 'decks') else 0,
                len(self.col.decks.all_config()) if hasattr(self.col, 'decks') else 0,
            ]
        except Exception as e:
            logger.error(f"Sanity check failed: {e}")
            return [list([0, 0, 0]), 0, 0, 0, 0, 0, 0, 0]

    def usnLim(self):
        return "usn >= -1"

    def finish(self, now=None):
        if now is not None:
            # ensure we save the mod time even if no changes made
            self.set_modified_time(now)
            self.set_last_sync(now)
            self.increment_usn()
            self.col.save()
            return now
        # even though that now is None will not happen,have to match a gurad case
        return None

    # Chunked syncing
    ##########################################################################

    def prepareToChunk(self):
        self.tablesLeft = ["revlog", "cards", "notes"]
        self.cursor = None

    def queryTable(self, table):
        lim = self.usnLim()
        
        # Use schema updater for dynamic field selection
        if table == "revlog":
            fields = self.schema_updater.get_query_fields("revlog")
            # Replace usn placeholder with actual value
            fields_with_usn = fields.replace("usn", "?")
            return self.col.db.execute(
                f"select {fields_with_usn} from revlog where {lim}",
                self.maxUsn,
            )
        elif table == "cards":
            fields = self.schema_updater.get_query_fields("cards")
            # Replace usn placeholder with actual value
            fields_with_usn = fields.replace("usn", "?")
            return self.col.db.execute(
                f"select {fields_with_usn} from cards where {lim}",
                self.maxUsn,
            )
        else:  # notes
            fields = self.schema_updater.get_query_fields("notes")
            # Replace usn placeholder with actual value
            fields_with_usn = fields.replace("usn", "?")
            return self.col.db.execute(
                f"select {fields_with_usn} from notes where {lim}",
                self.maxUsn,
            )

    def chunk(self):
        buf = dict(done=False)
        while self.tablesLeft:
            curTable = self.tablesLeft.pop()
            buf[curTable] = self.queryTable(curTable)
            self.col.db.execute(
                f"update {curTable} set usn=? where usn=-1", self.maxUsn
            )
        if not self.tablesLeft:
            buf["done"] = True
        return buf

    def applyChunk(self, chunk):
        if "revlog" in chunk:
            self.mergeRevlog(chunk["revlog"])
        if "cards" in chunk:
            self.mergeCards(chunk["cards"])
        if "notes" in chunk:
            self.mergeNotes(chunk["notes"])

    # Deletions
    ##########################################################################

    def add_grave(self, ids: List[int], type: int, usn: int):
        items = [(id, type, usn) for id in ids]
        # make sure table graves fields order and schema version match
        # query sql1='pragma table_info(graves)' version query schema='select ver from col'
        self.col.db.executemany(
            "INSERT OR IGNORE INTO graves (oid, type, usn) VALUES (?, ?, ?)", items
        )

    def apply_graves(self, graves, latest_usn: int):
        # remove card and the card's orphaned notes
        self.col.remove_cards_and_orphaned_notes(graves["cards"])
        self.add_grave(graves["cards"], REM_CARD, latest_usn)
        # only notes
        self.col.remove_notes(graves["notes"])
        self.add_grave(graves["notes"], REM_NOTE, latest_usn)

        # since level 0 deck ,we only remove deck ,but backend will delete child,it is ok, the delete
        # will have once effect
        self.col.decks.remove(graves["decks"])
        self.add_grave(graves["decks"], REM_DECK, latest_usn)

    # Models
    ##########################################################################

    def getModels(self):
        mods = [m for m in self.col.models.all() if m["usn"] == -1]
        for m in mods:
            m["usn"] = self.maxUsn
        self.col.models.save()
        return mods

    def mergeModels(self, rchg):
        for r in rchg:
            l = self.col.models.get(r["id"])
            # if missing locally or server is newer, update
            if not l or r["mod"] > l["mod"]:
                self.col.models.update(r)

    # Decks
    ##########################################################################

    def getDecks(self):
        decks = [g for g in self.col.decks.all() if g["usn"] == -1]
        for g in decks:
            g["usn"] = self.maxUsn
        dconf = [g for g in self.col.decks.allConf() if g["usn"] == -1]
        for g in dconf:
            g["usn"] = self.maxUsn
        self.col.decks.save()
        return [decks, dconf]

    def mergeDecks(self, rchg):
        for r in rchg[0]:
            l = self.col.decks.get(r["id"], False)
            # work around mod time being stored as string
            if l and not isinstance(l["mod"], int):
                l["mod"] = int(l["mod"])

            # if missing locally or server is newer, update
            if not l or r["mod"] > l["mod"]:
                self.col.decks.update(r)
        for r in rchg[1]:
            try:
                l = self.col.decks.getConf(r["id"])
            except KeyError:
                l = None
            # if missing locally or server is newer, update
            if not l or r["mod"] > l["mod"]:
                self.col.decks.updateConf(r)

    # Tags
    ##########################################################################
    def allItems(self) -> List[Tuple[str, int]]:
        tags = self.col.db.execute("select tag, usn from tags")
        return [(tag, int(usn)) for tag, usn in tags]

    def getTags(self):
        tags = []
        for t, usn in self.allItems():
            if usn == -1:
                self.col.tags.tags[t] = self.maxUsn
                tags.append(t)
        self.col.tags.save()
        return tags

    def mergeTags(self, tags):
        self.col.tags.register(tags, usn=self.maxUsn)

    # Cards/notes/revlog
    ##########################################################################

    def mergeRevlog(self, logs):
        # Validate and adjust revlog data for schema compatibility
        validated_logs = []
        for log_row in logs:
            validated_row = self.schema_updater.validate_row_data("revlog", log_row)
            validated_logs.append(validated_row)
        
        # Use dynamic placeholder generation
        placeholders = self.schema_updater.get_insert_placeholders("revlog")
        self.col.db.executemany(
            f"insert or ignore into revlog values ({placeholders})", 
            validated_logs
        )

    def newerRows(self, data, table, modIdx):
        ids = (r[0] for r in data)
        lmods = {}
        for id, mod in self.col.db.execute(
            "select id, mod from %s where id in %s and %s"
            % (table, ids2str(ids), self.usnLim())
        ):
            lmods[id] = mod
        update = []
        for r in data:
            if r[0] not in lmods or lmods[r[0]] < r[modIdx]:
                update.append(r)
        # replace col.log by just using print
        print(table, data)
        return update

    def mergeCards(self, cards):
        # Validate and adjust card data for schema compatibility
        validated_cards = []
        for card_row in self.newerRows(cards, "cards", 4):
            validated_row = self.schema_updater.validate_row_data("cards", card_row)
            validated_cards.append(validated_row)
        
        # Use dynamic placeholder generation
        placeholders = self.schema_updater.get_insert_placeholders("cards")
        self.col.db.executemany(
            f"insert or replace into cards values ({placeholders})",
            validated_cards,
        )

    def mergeNotes(self, notes):
        # Validate and adjust note data for schema compatibility
        validated_notes = []
        rows = self.newerRows(notes, "notes", 3)
        for note_row in rows:
            validated_row = self.schema_updater.validate_row_data("notes", note_row)
            validated_notes.append(validated_row)
        
        # Use dynamic placeholder generation
        placeholders = self.schema_updater.get_insert_placeholders("notes")
        self.col.db.executemany(
            f"insert or replace into notes values ({placeholders})", 
            validated_notes
        )
        self.col.after_note_updates(
            [f[0] for f in validated_notes], mark_modified=False, generate_cards=False
        )

    # Col config
    ##########################################################################

    def getConf(self):
        return self.col.conf

    def mergeConf(self, conf):
        for key, value in conf.items():
            self.col.set_config(key, value)


#         self.col.backend.set_all_config(json.dumps(conf).encode())

# Wrapper for requests that tracks upload/download progress
##########################################################################


class AnkiRequestsClient(object):
    verify = True
    timeout = 60

    def __init__(self):
        self.session = requests.Session()

    def post(self, url, data, headers):
        data = _MonitoringFile(data)
        headers["User-Agent"] = self._agentName()
        return self.session.post(
            url,
            data=data,
            headers=headers,
            stream=True,
            timeout=self.timeout,
            verify=self.verify,
        )

    def get(self, url, headers=None):
        if headers is None:
            headers = {}
        headers["User-Agent"] = self._agentName()
        return self.session.get(
            url, stream=True, headers=headers, timeout=self.timeout, verify=self.verify
        )

    def streamContent(self, resp):
        resp.raise_for_status()

        buf = io.BytesIO()
        for chunk in resp.iter_content(chunk_size=HTTP_BUF_SIZE):
            buf.write(chunk)
        return buf.getvalue()

    def _agentName(self):
        from anki import version

        return "Anki {}".format(version)


# allow user to accept invalid certs in work/school settings
if os.environ.get("ANKI_NOVERIFYSSL"):
    AnkiRequestsClient.verify = False

    import warnings

    warnings.filterwarnings("ignore")


class _MonitoringFile(io.BufferedReader):
    def read(self, size=-1):
        data = io.BufferedReader.read(self, HTTP_BUF_SIZE)

        return data


# HTTP syncing tools
##########################################################################


class HttpSyncer(object):
    def __init__(self, hkey=None, client=None, hostNum=None):
        self.hkey = hkey
        self.skey = checksum(str(random.random()))[:8]
        self.client = client or AnkiRequestsClient()
        self.postVars = {}
        self.hostNum = hostNum
        self.prefix = "sync/"

    def syncURL(self):
        if dev_mode:
            url = "https://l1sync.ankiweb.net/"
        else:
            url = SYNC_BASE % (self.hostNum or "")
        return url + self.prefix

    def assertOk(self, resp):
        # not using raise_for_status() as aqt expects this error msg
        if resp.status_code != 200:
            raise Exception("Unknown response code: %s" % resp.status_code)

    # Posting data as a file
    ######################################################################
    # We don't want to post the payload as a form var, as the percent-encoding is
    # costly. We could send it as a raw post, but more HTTP clients seem to
    # support file uploading, so this is the more compatible choice.

    def _buildPostData(self, fobj, comp):
        BOUNDARY = b"Anki-sync-boundary"
        bdry = b"--" + BOUNDARY
        buf = io.BytesIO()
        # post vars
        self.postVars["c"] = 1 if comp else 0
        for (key, value) in list(self.postVars.items()):
            buf.write(bdry + b"\r\n")
            buf.write(
                (
                    'Content-Disposition: form-data; name="%s"\r\n\r\n%s\r\n'
                    % (key, value)
                ).encode("utf8")
            )
        # payload as raw data or json
        rawSize = 0
        if fobj:
            # header
            buf.write(bdry + b"\r\n")
            buf.write(
                b"""\
Content-Disposition: form-data; name="data"; filename="data"\r\n\
Content-Type: application/octet-stream\r\n\r\n"""
            )
            # write file into buffer, optionally compressing
            if comp:
                tgt = gzip.GzipFile(mode="wb", fileobj=buf, compresslevel=comp)
            else:
                tgt = buf
            while 1:
                data = fobj.read(65536)
                if not data:
                    if comp:
                        tgt.close()
                    break
                rawSize += len(data)
                tgt.write(data)
            buf.write(b"\r\n")
        buf.write(bdry + b"--\r\n")
        size = buf.tell()
        # connection headers
        headers = {
            "Content-Type": "multipart/form-data; boundary=%s"
            % BOUNDARY.decode("utf8"),
            "Content-Length": str(size),
        }
        buf.seek(0)

        if size >= 100 * 1024 * 1024 or rawSize >= 250 * 1024 * 1024:
            raise Exception("Collection too large to upload to AnkiWeb.")

        return headers, buf

    def req(self, method, fobj=None, comp=6, badAuthRaises=True):
        headers, body = self._buildPostData(fobj, comp)

        r = self.client.post(self.syncURL() + method, data=body, headers=headers)
        if not badAuthRaises and r.status_code == 403:
            return False
        self.assertOk(r)

        buf = self.client.streamContent(r)
        return buf


# Incremental sync over HTTP
######################################################################


class RemoteServer(HttpSyncer):
    def __init__(self, hkey, hostNum):
        super().__init__(self, hkey, hostNum=hostNum)

    def hostKey(self, user, pw):
        "Returns hkey or none if user/pw incorrect."
        self.postVars = dict()
        ret = self.req(
            "hostKey",
            io.BytesIO(json.dumps(dict(u=user, p=pw)).encode("utf8")),
            badAuthRaises=False,
        )
        if not ret:
            # invalid auth
            return
        self.hkey = json.loads(ret.decode("utf8"))["key"]
        return self.hkey

    def meta(self):
        self.postVars = dict(
            k=self.hkey,
            s=self.skey,
        )
        ret = self.req(
            "meta",
            io.BytesIO(
                json.dumps(
                    dict(
                        v=SYNC_VER,
                        cv="ankidesktop,%s,%s" % (version_with_build(), plat_desc()),
                    )
                ).encode("utf8")
            ),
            badAuthRaises=False,
        )
        if not ret:
            # invalid auth
            return
        return json.loads(ret.decode("utf8"))

    def applyGraves(self, **kw):
        return self._run("applyGraves", kw)

    def applyChanges(self, **kw):
        return self._run("applyChanges", kw)

    def start(self, **kw):
        return self._run("start", kw)

    def chunk(self, **kw):
        return self._run("chunk", kw)

    def applyChunk(self, **kw):
        return self._run("applyChunk", kw)

    def sanityCheck2(self, **kw):
        return self._run("sanityCheck2", kw)

    def finish(self, **kw):
        return self._run("finish", kw)

    def abort(self, **kw):
        return self._run("abort", kw)

    def _run(self, cmd, data):
        return json.loads(
            self.req(cmd, io.BytesIO(json.dumps(data).encode("utf8"))).decode("utf8")
        )


# Full syncing
##########################################################################


class FullSyncer(HttpSyncer):
    def __init__(self, col, hkey, client, hostNum):
        super().__init__(self, hkey, client, hostNum=hostNum)
        self.postVars = dict(
            k=self.hkey,
            v="ankidesktop,%s,%s" % (anki.version, plat_desc()),
        )
        self.col = col

    def download(self):
        localNotEmpty = self.col.db.scalar("select 1 from cards")
        self.col.close()
        cont = self.req("download")
        tpath = self.col.path + ".tmp"
        if cont == "upgradeRequired":
            return
        open(tpath, "wb").write(cont)
        # check the received file is ok
        d = DB(tpath)
        assert d.scalar("pragma integrity_check") == "ok"
        remoteEmpty = not d.scalar("select 1 from cards")
        d.close()
        # accidental clobber?
        if localNotEmpty and remoteEmpty:
            os.unlink(tpath)
            return "downloadClobber"
        # overwrite existing collection
        os.unlink(self.col.path)
        os.rename(tpath, self.col.path)
        self.col = None

    def upload(self):
        "True if upload successful."
        # make sure it's ok before we try to upload
        if self.col.db.scalar("pragma integrity_check") != "ok":
            return False
        if not self.basicCheck():
            return False
        # apply some adjustments, then upload
        self.col.beforeUpload()
        if self.req("upload", open(self.col.path, "rb")) != b"OK":
            return False
        return True


# Remote media syncing
##########################################################################


class RemoteMediaServer(HttpSyncer):
    def __init__(self, col, hkey, client, hostNum):
        self.col = col
        super().__init__(self, hkey, client, hostNum=hostNum)
        self.prefix = "msync/"

    def begin(self):
        self.postVars = dict(
            k=self.hkey, v="ankidesktop,%s,%s" % (anki.version, plat_desc())
        )
        ret = self._dataOnly(
            self.req("begin", io.BytesIO(json.dumps(dict()).encode("utf8")))
        )
        self.skey = ret["sk"]
        return ret

    # args: lastUsn
    def mediaChanges(self, **kw):
        self.postVars = dict(
            sk=self.skey,
        )
        return self._dataOnly(
            self.req("mediaChanges", io.BytesIO(json.dumps(kw).encode("utf8")))
        )

    # args: files
    def downloadFiles(self, **kw):
        return self.req("downloadFiles", io.BytesIO(json.dumps(kw).encode("utf8")))

    def uploadChanges(self, zip):
        # no compression, as we compress the zip file instead
        return self._dataOnly(self.req("uploadChanges", io.BytesIO(zip), comp=0))

    # args: local
    def mediaSanity(self, **kw):
        return self._dataOnly(
            self.req("mediaSanity", io.BytesIO(json.dumps(kw).encode("utf8")))
        )

    def _dataOnly(self, resp):
        resp = json.loads(resp.decode("utf8"))
        if resp["err"]:
            self.col.log("error returned:%s" % resp["err"])
            raise Exception("SyncError:%s" % resp["err"])
        return resp["data"]

    # only for unit tests
    def mediatest(self, cmd):
        self.postVars = dict(
            k=self.hkey,
        )
        return self._dataOnly(
            self.req(
                "newMediaTest", io.BytesIO(json.dumps(dict(cmd=cmd)).encode("utf8"))
            )
        )

    # Enhanced sync features for modern Anki compatibility
    ##########################################################################

    def enhanced_changes(self):
        """Enhanced changes method that handles modern Anki sync requirements."""
        # Get basic changes
        changes = self.changes()
        
        # Add enhanced deck hierarchy and options sync
        if self.schema_updater.get_schema_version() >= 15:
            changes["deck_hierarchy"] = self.getDeckHierarchy()
            changes["deck_options"] = self.getDeckOptions()
        
        # Add note types and templates for modern schema
        if self.schema_updater.supports_table("notetypes"):
            changes["notetypes"] = self.getNotetypes()
            changes["templates"] = self.getTemplates()
            changes["fields"] = self.getFields()
        
        # Add enhanced tag sync for modern schema
        if self.schema_updater.get_schema_version() >= 17:
            changes["enhanced_tags"] = self.getEnhancedTags()
        
        # Add new card properties
        changes["card_properties"] = self.getCardProperties()
        
        return changes

    def enhanced_mergeChanges(self, lchg, rchg):
        """Enhanced merge changes that handles modern Anki sync requirements."""
        # Handle basic changes first
        self.mergeChanges(lchg, rchg)
        
        # Handle enhanced features
        if "deck_hierarchy" in rchg:
            self.mergeDeckHierarchy(rchg["deck_hierarchy"])
        
        if "deck_options" in rchg:
            self.mergeDeckOptions(rchg["deck_options"])
        
        if "notetypes" in rchg:
            self.mergeNotetypes(rchg["notetypes"])
        
        if "templates" in rchg:
            self.mergeTemplates(rchg["templates"])
        
        if "fields" in rchg:
            self.mergeFields(rchg["fields"])
        
        if "enhanced_tags" in rchg:
            self.mergeEnhancedTags(rchg["enhanced_tags"])
        
        if "card_properties" in rchg:
            self.mergeCardProperties(rchg["card_properties"])

    # Deck Hierarchy Sync
    ##########################################################################

    def getDeckHierarchy(self):
        """Get deck hierarchy information for sync."""
        try:
            # Get all decks with hierarchy information
            hierarchy = []
            for deck in self.col.decks.all():
                if deck["usn"] == -1:
                    deck_info = {
                        "id": deck["id"],
                        "name": deck["name"],
                        "parent_id": self._get_parent_deck_id(deck["name"]),
                        "level": len(deck["name"].split("::")),
                        "collapsed": deck.get("collapsed", False),
                        "usn": self.maxUsn
                    }
                    hierarchy.append(deck_info)
                    deck["usn"] = self.maxUsn
            
            self.col.decks.save()
            return hierarchy
        except Exception as e:
            logger.error(f"Error getting deck hierarchy: {e}")
            return []

    def _get_parent_deck_id(self, deck_name):
        """Get parent deck ID from deck name."""
        parts = deck_name.split("::")
        if len(parts) <= 1:
            return None  # Top-level deck
        
        parent_name = "::".join(parts[:-1])
        parent_deck = self.col.decks.by_name(parent_name)
        return parent_deck["id"] if parent_deck else None

    def mergeDeckHierarchy(self, hierarchy):
        """Merge deck hierarchy information."""
        try:
            for deck_info in hierarchy:
                # Update deck hierarchy information
                deck = self.col.decks.get(deck_info["id"])
                if deck:
                    # Update collapsed state and other hierarchy properties
                    if "collapsed" in deck_info:
                        deck["collapsed"] = deck_info["collapsed"]
                    
                    # Ensure parent-child relationships are maintained
                    if deck_info.get("parent_id"):
                        parent_deck = self.col.decks.get(deck_info["parent_id"])
                        if parent_deck:
                            # Verify name hierarchy matches
                            expected_name = f"{parent_deck['name']}::{deck['name'].split('::')[-1]}"
                            if deck["name"] != expected_name:
                                logger.info(f"Updating deck name hierarchy: {deck['name']} -> {expected_name}")
                                deck["name"] = expected_name
                    
                    self.col.decks.save(deck)
        except Exception as e:
            logger.error(f"Error merging deck hierarchy: {e}")

    # Deck Options Sync
    ##########################################################################

    def getDeckOptions(self):
        """Get deck options/configuration for sync."""
        try:
            options = []
            
            # Get deck configurations
            for conf in self.col.decks.allConf():
                if conf["usn"] == -1:
                    conf["usn"] = self.maxUsn
                    options.append(conf)
            
            # Get deck-specific options
            for deck in self.col.decks.all():
                if deck["usn"] == -1:
                    deck_options = {
                        "deck_id": deck["id"],
                        "config_id": deck.get("conf", 1),
                        "options": {
                            "desc": deck.get("desc", ""),
                            "dyn": deck.get("dyn", 0),
                            "extendNew": deck.get("extendNew", 10),
                            "extendRev": deck.get("extendRev", 50),
                        },
                        "usn": self.maxUsn
                    }
                    options.append(deck_options)
            
            self.col.decks.save()
            return options
        except Exception as e:
            logger.error(f"Error getting deck options: {e}")
            return []

    def mergeDeckOptions(self, options):
        """Merge deck options/configuration."""
        try:
            for option in options:
                if "config_id" in option:
                    # This is a deck configuration
                    existing_conf = None
                    try:
                        existing_conf = self.col.decks.getConf(option["config_id"])
                    except KeyError:
                        pass
                    
                    if not existing_conf or option.get("mod", 0) > existing_conf.get("mod", 0):
                        self.col.decks.updateConf(option)
                
                elif "deck_id" in option:
                    # This is deck-specific options
                    deck = self.col.decks.get(option["deck_id"])
                    if deck:
                        deck_options = option.get("options", {})
                        for key, value in deck_options.items():
                            deck[key] = value
                        self.col.decks.save(deck)
        except Exception as e:
            logger.error(f"Error merging deck options: {e}")

    # Note Types/Templates Sync (for modern schema)
    ##########################################################################

    def getNotetypes(self):
        """Get note types for sync (modern schema V15+)."""
        if not self.schema_updater.supports_table("notetypes"):
            return []
        
        try:
            notetypes = []
            # Query notetypes table directly for modern schema
            for row in self.col.db.execute("SELECT id, name, mtime_secs, usn, config FROM notetypes WHERE usn = -1"):
                notetype = {
                    "id": row[0],
                    "name": row[1],
                    "mtime_secs": row[2],
                    "usn": self.maxUsn,
                    "config": row[4]
                }
                notetypes.append(notetype)
                # Update USN
                self.col.db.execute("UPDATE notetypes SET usn = ? WHERE id = ?", self.maxUsn, row[0])
            
            return notetypes
        except Exception as e:
            logger.error(f"Error getting notetypes: {e}")
            return []

    def getTemplates(self):
        """Get templates for sync (modern schema V15+)."""
        if not self.schema_updater.supports_table("templates"):
            return []
        
        try:
            templates = []
            for row in self.col.db.execute("SELECT ntid, ord, name, mtime_secs, usn, config FROM templates WHERE usn = -1"):
                template = {
                    "ntid": row[0],
                    "ord": row[1],
                    "name": row[2],
                    "mtime_secs": row[3],
                    "usn": self.maxUsn,
                    "config": row[5]
                }
                templates.append(template)
                # Update USN
                self.col.db.execute("UPDATE templates SET usn = ? WHERE ntid = ? AND ord = ?", self.maxUsn, row[0], row[1])
            
            return templates
        except Exception as e:
            logger.error(f"Error getting templates: {e}")
            return []

    def getFields(self):
        """Get fields for sync (modern schema V15+)."""
        if not self.schema_updater.supports_table("fields"):
            return []
        
        try:
            fields = []
            for row in self.col.db.execute("SELECT ntid, ord, name, config FROM fields"):
                field = {
                    "ntid": row[0],
                    "ord": row[1],
                    "name": row[2],
                    "config": row[3]
                }
                fields.append(field)
            
            return fields
        except Exception as e:
            logger.error(f"Error getting fields: {e}")
            return []

    def mergeNotetypes(self, notetypes):
        """Merge note types (modern schema V15+)."""
        if not self.schema_updater.supports_table("notetypes"):
            return
        
        try:
            for nt in notetypes:
                # Check if notetype exists
                existing = self.col.db.scalar("SELECT mtime_secs FROM notetypes WHERE id = ?", nt["id"])
                
                if not existing or nt.get("mtime_secs", 0) > existing:
                    # Insert or update notetype
                    self.col.db.execute("""
                        INSERT OR REPLACE INTO notetypes (id, name, mtime_secs, usn, config)
                        VALUES (?, ?, ?, ?, ?)
                    """, nt["id"], nt["name"], nt["mtime_secs"], nt["usn"], nt["config"])
        except Exception as e:
            logger.error(f"Error merging notetypes: {e}")

    def mergeTemplates(self, templates):
        """Merge templates (modern schema V15+)."""
        if not self.schema_updater.supports_table("templates"):
            return
        
        try:
            for tmpl in templates:
                # Check if template exists
                existing = self.col.db.scalar("SELECT mtime_secs FROM templates WHERE ntid = ? AND ord = ?", 
                                            tmpl["ntid"], tmpl["ord"])
                
                if not existing or tmpl.get("mtime_secs", 0) > existing:
                    # Insert or update template
                    self.col.db.execute("""
                        INSERT OR REPLACE INTO templates (ntid, ord, name, mtime_secs, usn, config)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, tmpl["ntid"], tmpl["ord"], tmpl["name"], tmpl["mtime_secs"], tmpl["usn"], tmpl["config"])
        except Exception as e:
            logger.error(f"Error merging templates: {e}")

    def mergeFields(self, fields):
        """Merge fields (modern schema V15+)."""
        if not self.schema_updater.supports_table("fields"):
            return
        
        try:
            for field in fields:
                # Insert or update field
                self.col.db.execute("""
                    INSERT OR REPLACE INTO fields (ntid, ord, name, config)
                    VALUES (?, ?, ?, ?)
                """, field["ntid"], field["ord"], field["name"], field["config"])
        except Exception as e:
            logger.error(f"Error merging fields: {e}")

    # Enhanced Tags Sync (for modern schema V17+)
    ##########################################################################

    def getEnhancedTags(self):
        """Get enhanced tags for sync (modern schema V17+)."""
        if self.schema_updater.get_schema_version() < 17:
            return self.getTags()  # Fall back to legacy tags
        
        try:
            tags = []
            for row in self.col.db.execute("SELECT tag, usn, collapsed, config FROM tags WHERE usn = -1"):
                tag_info = {
                    "tag": row[0],
                    "usn": self.maxUsn,
                    "collapsed": row[2] if len(row) > 2 else 0,
                    "config": row[3] if len(row) > 3 else b''
                }
                tags.append(tag_info)
                # Update USN
                self.col.db.execute("UPDATE tags SET usn = ? WHERE tag = ?", self.maxUsn, row[0])
            
            return tags
        except Exception as e:
            logger.error(f"Error getting enhanced tags: {e}")
            return self.getTags()  # Fall back to legacy

    def mergeEnhancedTags(self, tags):
        """Merge enhanced tags (modern schema V17+)."""
        if self.schema_updater.get_schema_version() < 17:
            # Fall back to legacy tag merge
            tag_names = [tag["tag"] for tag in tags if "tag" in tag]
            self.mergeTags(tag_names)
            return
        
        try:
            for tag_info in tags:
                # Insert or update enhanced tag
                self.col.db.execute("""
                    INSERT OR REPLACE INTO tags (tag, usn, collapsed, config)
                    VALUES (?, ?, ?, ?)
                """, tag_info["tag"], tag_info["usn"], 
                    tag_info.get("collapsed", 0), tag_info.get("config", b''))
        except Exception as e:
            logger.error(f"Error merging enhanced tags: {e}")

    # Card Properties Sync
    ##########################################################################

    def getCardProperties(self):
        """Get new card properties for sync."""
        try:
            properties = {}
            
            # Get card scheduling properties that may be new
            card_fields = self.schema_updater._field_mappings.get("cards", [])
            
            # Check for new fields that might not be in legacy sync
            new_fields = []
            for field in card_fields:
                if field not in ["id", "nid", "did", "ord", "mod", "usn", "type", "queue", 
                               "due", "ivl", "factor", "reps", "lapses", "left", "odue", "odid", "flags", "data"]:
                    new_fields.append(field)
            
            if new_fields:
                properties["new_card_fields"] = new_fields
                logger.info(f"Found new card fields for sync: {new_fields}")
            
            # Get any collection-level card properties
            try:
                card_config = self.col.get_config("cardConfig", {})
                if card_config:
                    properties["card_config"] = card_config
            except:
                pass
            
            return properties
        except Exception as e:
            logger.error(f"Error getting card properties: {e}")
            return {}

    def mergeCardProperties(self, properties):
        """Merge new card properties."""
        try:
            if "new_card_fields" in properties:
                logger.info(f"Merging new card fields: {properties['new_card_fields']}")
                # New fields are handled automatically by schema updater
            
            if "card_config" in properties:
                self.col.set_config("cardConfig", properties["card_config"])
        except Exception as e:
            logger.error(f"Error merging card properties: {e}")

    # Enhanced Conflict Resolution
    ##########################################################################

    def detect_full_sync_required(self, server_meta, client_meta):
        """Detect when a full sync is required due to conflicts or schema differences."""
        try:
            # Check schema compatibility
            server_scm = server_meta.get("scm", 0)
            client_scm = client_meta.get("scm", 0)
            
            # If schema modification times differ significantly, full sync needed
            if abs(server_scm - client_scm) > 86400:  # More than 1 day difference
                logger.warning(f"Schema modification time difference too large: server={server_scm}, client={client_scm}")
                return True, "Schema modification times differ significantly"
            
            # Check for collection divergence
            server_usn = server_meta.get("usn", 0)
            client_usn = client_meta.get("usn", 0)
            
            # If USN difference is too large, collections may have diverged
            if abs(server_usn - client_usn) > 1000:  # Arbitrary threshold
                logger.warning(f"USN difference too large: server={server_usn}, client={client_usn}")
                return True, "Collections have diverged significantly"
            
            # Check schema version compatibility
            server_schema_version = self.schema_updater.get_schema_version()
            client_schema_version = client_meta.get("schema_version", 11)  # Default to V11
            
            schema_compat = self.schema_updater.handle_schema_incompatibility(
                client_schema_version, server_schema_version
            )
            
            if not schema_compat["compatible"] and schema_compat["requires_full_sync"]:
                return True, schema_compat["error"]
            
            # Check for data migration needs
            if self.schema_updater.needs_data_migration():
                logger.info("Data migration needed - recommending full sync")
                return True, "Data migration required between JSON and table storage"
            
            return False, None
            
        except Exception as e:
            logger.error(f"Error detecting full sync requirement: {e}")
            return True, f"Error during conflict detection: {e}"

    def enhanced_conflict_resolution(self, local_changes, remote_changes):
        """Enhanced conflict resolution using Anki's merge logic."""
        try:
            conflicts_detected = []
            resolution_actions = []
            
            # Check for model/notetype conflicts
            if "models" in local_changes and "models" in remote_changes:
                model_conflicts = self._detect_model_conflicts(
                    local_changes["models"], remote_changes["models"]
                )
                conflicts_detected.extend(model_conflicts)
            
            # Check for deck conflicts
            if "decks" in local_changes and "decks" in remote_changes:
                deck_conflicts = self._detect_deck_conflicts(
                    local_changes["decks"], remote_changes["decks"]
                )
                conflicts_detected.extend(deck_conflicts)
            
            # Check for tag conflicts
            if "tags" in local_changes and "tags" in remote_changes:
                tag_conflicts = self._detect_tag_conflicts(
                    local_changes["tags"], remote_changes["tags"]
                )
                conflicts_detected.extend(tag_conflicts)
            
            # Resolve conflicts using modification time preference
            for conflict in conflicts_detected:
                action = self._resolve_conflict_by_mod_time(conflict)
                resolution_actions.append(action)
            
            return {
                "conflicts": conflicts_detected,
                "actions": resolution_actions,
                "requires_full_sync": len([c for c in conflicts_detected if c["severity"] == "high"]) > 0
            }
            
        except Exception as e:
            logger.error(f"Error in conflict resolution: {e}")
            return {
                "conflicts": [],
                "actions": [],
                "requires_full_sync": True,
                "error": str(e)
            }

    def _detect_model_conflicts(self, local_models, remote_models):
        """Detect conflicts in models/notetypes."""
        conflicts = []
        
        # Create lookup maps
        local_map = {m["id"]: m for m in local_models}
        remote_map = {m["id"]: m for m in remote_models}
        
        # Check for conflicts
        for model_id in set(local_map.keys()) & set(remote_map.keys()):
            local_model = local_map[model_id]
            remote_model = remote_map[model_id]
            
            # Compare modification times
            local_mod = local_model.get("mod", 0)
            remote_mod = remote_model.get("mod", 0)
            
            if local_mod != remote_mod:
                # Check if this is a significant conflict
                severity = "low"
                if abs(local_mod - remote_mod) > 3600:  # More than 1 hour difference
                    severity = "medium"
                
                # Check for structural changes
                if (local_model.get("flds", []) != remote_model.get("flds", []) or
                    local_model.get("tmpls", []) != remote_model.get("tmpls", [])):
                    severity = "high"
                
                conflicts.append({
                    "type": "model",
                    "id": model_id,
                    "name": local_model.get("name", "Unknown"),
                    "severity": severity,
                    "local_mod": local_mod,
                    "remote_mod": remote_mod,
                    "local_data": local_model,
                    "remote_data": remote_model
                })
        
        return conflicts

    def _detect_deck_conflicts(self, local_decks, remote_decks):
        """Detect conflicts in decks."""
        conflicts = []
        
        # Handle deck array format [decks, dconf]
        local_deck_list = local_decks[0] if isinstance(local_decks, list) else local_decks
        remote_deck_list = remote_decks[0] if isinstance(remote_decks, list) else remote_decks
        
        # Create lookup maps
        local_map = {d["id"]: d for d in local_deck_list}
        remote_map = {d["id"]: d for d in remote_deck_list}
        
        # Check for conflicts
        for deck_id in set(local_map.keys()) & set(remote_map.keys()):
            local_deck = local_map[deck_id]
            remote_deck = remote_map[deck_id]
            
            # Compare modification times
            local_mod = local_deck.get("mod", 0)
            remote_mod = remote_deck.get("mod", 0)
            
            if local_mod != remote_mod:
                severity = "low"
                if abs(local_mod - remote_mod) > 3600:  # More than 1 hour difference
                    severity = "medium"
                
                # Check for name conflicts (hierarchy changes)
                if local_deck.get("name") != remote_deck.get("name"):
                    severity = "high"
                
                conflicts.append({
                    "type": "deck",
                    "id": deck_id,
                    "name": local_deck.get("name", "Unknown"),
                    "severity": severity,
                    "local_mod": local_mod,
                    "remote_mod": remote_mod,
                    "local_data": local_deck,
                    "remote_data": remote_deck
                })
        
        return conflicts

    def _detect_tag_conflicts(self, local_tags, remote_tags):
        """Detect conflicts in tags."""
        conflicts = []
        
        # For simple tag lists
        if isinstance(local_tags, list) and isinstance(remote_tags, list):
            # Check for tag differences
            local_set = set(local_tags)
            remote_set = set(remote_tags)
            
            if local_set != remote_set:
                conflicts.append({
                    "type": "tags",
                    "severity": "low",
                    "local_data": local_tags,
                    "remote_data": remote_tags,
                    "added_locally": list(local_set - remote_set),
                    "added_remotely": list(remote_set - local_set)
                })
        
        return conflicts

    def _resolve_conflict_by_mod_time(self, conflict):
        """Resolve conflict by preferring the more recent modification time."""
        local_mod = conflict.get("local_mod", 0)
        remote_mod = conflict.get("remote_mod", 0)
        
        if remote_mod > local_mod:
            return {
                "conflict_id": conflict.get("id"),
                "action": "use_remote",
                "reason": f"Remote modification time ({remote_mod}) is newer than local ({local_mod})"
            }
        elif local_mod > remote_mod:
            return {
                "conflict_id": conflict.get("id"),
                "action": "use_local",
                "reason": f"Local modification time ({local_mod}) is newer than remote ({remote_mod})"
            }
        else:
            return {
                "conflict_id": conflict.get("id"),
                "action": "use_remote",  # Default to remote in case of tie
                "reason": "Modification times equal, defaulting to remote"
            }

    def handle_collection_divergence(self, server_state, client_state):
        """Handle cases where collections have diverged significantly."""
        try:
            divergence_indicators = []
            
            # Check USN gaps
            server_usn = server_state.get("usn", 0)
            client_usn = client_state.get("usn", 0)
            usn_gap = abs(server_usn - client_usn)
            
            if usn_gap > 100:  # Significant USN gap
                divergence_indicators.append({
                    "type": "usn_gap",
                    "severity": "high" if usn_gap > 1000 else "medium",
                    "description": f"USN gap of {usn_gap} detected",
                    "server_usn": server_usn,
                    "client_usn": client_usn
                })
            
            # Check modification time differences
            server_mod = server_state.get("mod", 0)
            client_mod = client_state.get("mod", 0)
            mod_diff = abs(server_mod - client_mod)
            
            if mod_diff > 86400:  # More than 1 day difference
                divergence_indicators.append({
                    "type": "mod_time_diff",
                    "severity": "medium",
                    "description": f"Modification time difference of {mod_diff} seconds",
                    "server_mod": server_mod,
                    "client_mod": client_mod
                })
            
            # Check schema compatibility
            schema_info = self.schema_updater.get_schema_compatibility_info()
            if not schema_info["is_compatible"]:
                divergence_indicators.append({
                    "type": "schema_incompatible",
                    "severity": "high",
                    "description": "Schema versions are incompatible",
                    "schema_info": schema_info
                })
            
            # Determine recommended action
            high_severity_count = len([i for i in divergence_indicators if i["severity"] == "high"])
            
            if high_severity_count > 0:
                recommendation = "full_sync_required"
                message = "Collections have diverged significantly. Full sync required."
            elif len(divergence_indicators) > 2:
                recommendation = "full_sync_recommended"
                message = "Multiple divergence indicators detected. Full sync recommended."
            else:
                recommendation = "incremental_sync_possible"
                message = "Minor divergence detected. Incremental sync may be possible."
            
            return {
                "diverged": len(divergence_indicators) > 0,
                "indicators": divergence_indicators,
                "recommendation": recommendation,
                "message": message,
                "requires_user_choice": high_severity_count > 0
            }
            
        except Exception as e:
            logger.error(f"Error handling collection divergence: {e}")
            return {
                "diverged": True,
                "recommendation": "full_sync_required",
                "message": f"Error analyzing divergence: {e}",
                "requires_user_choice": True
            }

    def should_abort_sync(self, conflict_analysis, divergence_analysis):
        """Determine if sync should be aborted and user prompted for upload/download choice."""
        try:
            # Abort if high-severity conflicts detected
            if conflict_analysis.get("requires_full_sync", False):
                return True, "High-severity conflicts require full sync"
            
            # Abort if collection divergence requires user choice
            if divergence_analysis.get("requires_user_choice", False):
                return True, divergence_analysis.get("message", "Collection divergence detected")
            
            # Abort if schema migration needed
            if self.schema_updater.needs_data_migration():
                return True, "Data migration required - full sync needed"
            
            return False, None
            
        except Exception as e:
            logger.error(f"Error determining sync abort: {e}")
            return True, f"Error in sync analysis: {e}"

    def maxUsn(self):
        return self.col._usn

    def mediaChanges(self, lastUsn):
        result = []
        usn = lastUsn + 1
        fname = None
        while fname is not None or lastUsn == 0:
            fname = self.col.media.syncMedia(lastUsn)
            if fname is not None:
                result.append(fname)
                lastUsn = usn
                usn += 1
        return {"files": result, "lastUsn": lastUsn}
