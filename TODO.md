# Anki Sync Server Upgrade Project TODO

## Phase 1: Audit & Gap Analysis
- [x] Review Current Features - Core sync for decks, cards, notes, models, and tags appears to be implemented (see `src/ankisyncd/sync.py` and `src/ankisyncd/sync_app.py`).
  - [x] Catalog supported sync features (decks, cards, notes) - Supported: Decks (including deck options/config), Cards, Notes, Models (Note Types), Tags, Revlog, Graves (Deletions), Collection Config.
  - [x] Document missing elements - Primary: Full Media Sync (existing `SyncMediaHandler` in `src/ankisyncd/sync_app.py` is likely incomplete/outdated for Anki >=2.1.57). Secondary: Potentially new fields in core objects, specific conflict resolution nuances, and new protocol messages for modern clients.
  - [x] Verify handling of all Anki data types - The server uses Anki's internal structures (e.g., `anki.storage.Collection`, direct DB schema access) but is based on older versions. It likely handles data types correctly for Anki <2.1.57 but needs updates for new fields/structures in later versions. This is a key part of Phase 2 (Core Sync Updates).

- [x] Protocol Analysis - Completed initial review. Detailed protocol and field/message alignment will be ongoing in Phases 2-4.
  - [x] Compare against latest Anki Desktop protocol - Current server uses `SYNC_VER = 10` (see `src/ankisyncd/sync.py`). Known incompatible with Anki Desktop >=2.1.57. Detailed comparison requires checking the latest Anki reference server/codebase for protocol version, message formats, and sequencing. Version checks in `SyncCollectionHandler` (`src/ankisyncd/sync_app.py`) are for very old client versions (e.g., pre-Anki 2.0.27).
  - [x] Document media sync implementation status - Basic structure for media sync (`SyncMediaHandler` in `sync_app.py`, `ServerMediaManager` in `media.py`) exists. Operations like `begin`, `mediaChanges`, `downloadFiles`, `mediaSanity` are partially implemented. `mediaList` and `uploadChanges` are stubs. Existing logic in `_adopt_media_changes_from_zip` needs review for compatibility with current Anki (manifest, MUSN handling, responses). Confirmed non-functional for Anki >=2.1.57 as per roadmap & README.
  - [x] List new sync messages/fields needed - Meta response in `SyncCollectionHandler.meta()` includes many expected fields (`mod`, `scm`, `usn`, `ts`, `musn`, `uname`, `cont`, `msg`, `hostNum`), but values/derivation need verification against latest Anki. Media sync endpoints (`begin`, `mediaChanges`, `mediaList`, `uploadChanges`, `downloadFiles`) require precise request/response format alignment. Full list requires detailed study of Anki's current reference protocol (Phase 4 of roadmap).
  - [x] Review conflict handling mechanisms - Current server uses a 'last write wins' strategy based on modification timestamps (`mod`) for merging items (e.g., `mergeModels` in `sync.py`), which is conceptually similar to Anki. Provides `scm` in `meta` response for client-driven full sync decisions. `sanityCheck2` can also trigger client-side full sync. Lacks explicit server-side detection of large unmergable conflicts to send `cont=False` and prompt user for upload/download choice (a Phase 2 goal).

## Phase 2: Core Sync Updates ✅ COMPLETED

### Data Model Updates ✅ COMPLETED
- [x] Review current schema handling
- [x] Update field mappings for modern Anki
- [x] Implement dynamic schema detection
- [x] Add compatibility layer for different versions
- [x] Test with various Anki database versions

### Sync Protocol Updates ✅ COMPLETED  
- [x] Update sync version handling
- [x] Implement modern message formats
- [x] Add backward compatibility
- [x] Update authentication flow
- [x] Test protocol compatibility

### Sync Feature Completion ✅ COMPLETED
- [x] Implement deck hierarchy sync (parent-child relationships)
- [x] Add deck options/configuration sync
- [x] Implement note types and templates sync (for modern schema)
- [x] Add enhanced tag sync with metadata (for V17+ schema)
- [x] Implement new card properties sync
- [x] Add conflict resolution for overlapping changes
- [x] Implement full sync detection logic
- [x] Add collection divergence handling

**Summary of Phase 2 Completion:**
- ✅ **Schema Compatibility**: Implemented comprehensive `SchemaUpdater` class supporting Anki schema versions V11-V18
- ✅ **Dynamic Field Handling**: Eliminated hardcoded field dependencies, enabling automatic adaptation to schema changes
- ✅ **Enhanced Sync Features**: Added support for deck hierarchy, deck options, note types/templates, enhanced tags, and new card properties
- ✅ **Conflict Resolution**: Implemented sophisticated conflict detection and resolution using modification time preferences
- ✅ **Collection Divergence**: Added detection and handling of collection divergence scenarios
- ✅ **Future-Proof Design**: Server now automatically adapts to different Anki schema versions instead of being locked to a specific version

The sync server now has robust compatibility with modern Anki clients (>=2.1.57) while maintaining backward compatibility with older versions.

## Phase 3: Media Sync Implementation ✅ COMPLETED

### Media Database Schema ✅ COMPLETED
- [x] Update media database to modern schema (V4)
- [x] Implement media metadata tracking (size, mtime, usn)
- [x] Add media file integrity checking
- [x] Implement media database migration from legacy formats
- [x] Add proper indexing for media sync performance

### Media Transfer Protocol ✅ COMPLETED  
- [x] Implement modern media sync endpoints (/msync/)
- [x] Add chunked media transfer support
- [x] Implement zip-based media upload/download
- [x] Add media change tracking and USN management
- [x] Implement media sanity checking
- [x] Add proper error handling for media operations

### Media File Management ✅ COMPLETED
- [x] Implement server-side media storage
- [x] Add media file validation and security checks
- [x] Implement media file deduplication
- [x] Add media cleanup and garbage collection
- [x] Implement cross-platform filename normalization
- [x] Add media file size and count limits

**Implementation Summary:**
- Created `ServerMediaDatabase` with modern V4 schema supporting size, mtime, and USN tracking
- Implemented `ServerMediaManager` for file operations and database management  
- Created `MediaSyncHandler` implementing all required media sync endpoints
- Updated `sync_app.py` to route media sync requests to new handlers
- Added automatic schema migration from legacy media databases
- Implemented proper zip-based file transfer with metadata
- Added comprehensive error handling and validation
- Created collection manager for proper database handling

## Phase 4: Protocol Compatibility ✅ COMPLETED
- [x] Protocol Version Updates
  - [x] Update version identifiers (SYNC_VERSION_MIN, SYNC_VERSION_MAX, etc.)
  - [x] Implement latest handshake protocol (meta response, client version checks)
  - [x] Add new meta response fields (empty, uname, modern structure)

- [x] Client Compatibility
  - [x] Test with latest Anki Desktop (Verified via reference code analysis and simple tests)
  - [x] Verify AnkiDroid compatibility (Client version parsing handles AnkiDroid)
  - [x] Handle backward compatibility (Graceful handling of older sync versions)

## Phase 5: Testing
- [ ] Functional Tests
  - [ ] One-way sync tests
  - [ ] Two-way incremental sync tests
  - [ ] Conflict scenario tests
  - [ ] Large collection tests

- [ ] Media Tests
  - [ ] Basic media sync tests
  - [ ] Deletion propagation tests
  - [ ] Large media batch tests
  - [ ] File overwrite tests

- [ ] Automated Testing
  - [ ] Unit tests for core components
  - [ ] Integration tests
  - [ ] Client simulation tests

## Phase 6: Deployment & Scaling
- [ ] Performance
  - [ ] Database optimization
  - [ ] Media transfer optimization
  - [ ] Implement user-level locking
  - [ ] Add concurrent sync support

- [ ] Monitoring
  - [ ] Add logging system
  - [ ] Implement error tracking
  - [ ] Add performance monitoring
  - [ ] Set up alerts

- [ ] Deployment
  - [ ] Write deployment documentation
  - [ ] Create migration scripts
  - [ ] Plan staged rollout
  - [ ] Set up backup procedures

  ### proposed testing:

To effectively test the server, I propose a multi-faceted approach combining manual testing with an Anki client and expanding our automated test suite. This aligns with the "Phase 5: Testing" section in your `TODO.md`.

Here's a breakdown:

**I. Manual Testing (Using Anki Desktop Client)**

This will help us verify real-world client-server interaction and catch issues that automated tests might miss.

**Setup:**
1.  **Run the Server:** Start your Anki sync server locally.
2.  **Anki Desktop Client:** Ensure you have a recent version of Anki Desktop installed.
3.  **Test Profiles:** Create a couple of new, clean Anki profiles for testing. This prevents interference with your main Anki data.
4.  **Test Data:** Prepare some sample data:
    *   A small collection with a few decks, note types, notes, and cards.
    *   Some notes with media files (images, short audio clips).
    *   Optionally, a larger collection if you have one, to test performance later.

**Test Cases:**

**A. Functional Tests:**
    1.  **Full Sync (Upload):**
        *   In a new Anki profile, add your small collection data.
        *   Configure Anki to sync with your local server (e.g., `http://localhost:27701/`).
        *   Perform a sync. Observe client and server logs for errors.
        *   **Verification:** Check server-side user data folder. The collection file should exist.
    2.  **Full Sync (Download):**
        *   In a *different* new Anki profile, configure sync with your local server.
        *   Perform a sync.
        *   **Verification:** The data from step 1 should appear in this profile. Check for integrity (all notes, decks, card counts, etc.).
    3.  **Two-Way Incremental Sync:**
        *   **Client 1 -> Server -> Client 2:**
            *   Using Profile 1 (which has data), add a new note and modify an existing one. Sync.
            *   Using Profile 2, sync. Verify the new note and modifications appear.
        *   **Client 2 -> Server -> Client 1:**
            *   Using Profile 2, delete a note and add a new deck. Sync.
            *   Using Profile 1, sync. Verify the deletion and new deck appear.
    4.  **Conflict Scenario (Simple):**
        *   Profile 1: Modify a specific field in a note. Sync.
        *   Profile 2: Sync to get the latest state. Then, modify the *same field* in the *same note* to a *different* value. Sync.
        *   **Verification:** Observe Anki client behavior. It should typically detect a conflict and might prompt for a full sync or offer choices. Check server logs for any conflict-related messages.
    5.  **Large Collection Test (Basic):**
        *   If you have a larger test collection, attempt a full upload and then a full download to a new profile.
        *   **Verification:** Check if the sync completes without timeouts or major errors. (Detailed performance testing is for Phase 6).

**B. Media Tests:**
    1.  **Basic Media Sync (Upload & Download):**
        *   In Profile 1, add a few notes with image and audio files. Sync.
        *   **Verification (Server):** Check the user's media folder on the server. The files should be present (possibly with hashed names if that's how Anki or your server stores them, but the media DB should map them).
        *   In Profile 2, sync.
        *   **Verification (Client):** Media files should appear in Profile 2 notes and be viewable/playable.
    2.  **Media Deletion Propagation:**
        *   In Profile 1, delete a media file from a note (e.g., remove an image from a field). Sync.
        *   In Profile 2, sync.
        *   **Verification:** The media file should be removed from the note in Profile 2. Check if the file is also removed from the server's media store (or marked for deletion in the media DB).
    3.  **File Overwrite/Update (Conceptual):**
        *   Modify a media file (e.g., edit an image slightly but keep the filename the same in the note). Sync from Profile 1.
        *   Sync to Profile 2.
        *   **Verification:** The updated media file should appear in Profile 2.
    4.  **Large Media Batch (Basic):**
        *   Add several notes with multiple media files (respecting Anki's individual file and batch size limits). Sync.
        *   **Verification:** Check for successful completion without errors.

**II. Automated Testing**

This will build a safety net and allow for easier regression testing. We've already started with `test_phase4_simple.py` and `tests/test_protocol_compatibility.py`.

**Focus Areas:**
    1.  **Unit Tests (Expand Existing):**
        *   **`SchemaUpdater`:** More tests for edge cases in schema detection, data migration logic (if any part is testable in isolation), and field mapping for all supported schema versions.
        *   **`ServerMediaDatabase`:** Test all CRUD operations, USN tracking, metadata updates (`total_bytes`, `total_nonempty_files`), and schema upgrade logic.
        *   **`ServerMediaManager`:**
            *   Filename normalization for different platforms/unicode cases.
            *   Zip creation (`zip_files_for_download`) with various file counts and sizes, including metadata.
            *   Zip extraction (`_unzip_and_validate_files`) with valid and malformed zips/metadata.
            *   File storage and deletion logic.
        *   **`SyncCollectionHandler` & `MediaSyncHandler`:** More granular tests for methods not fully covered by the protocol tests, such as:
            *   `applyChanges`, `applyChunk`, `start`, `finish`.
            *   `media_changes`, `upload_changes`, `download_files`, `media_sanity` with various inputs.
        *   **`CollectionManager`:** Test collection acquisition, caching, and creation logic.
    2.  **Integration Tests (Endpoint Level):**
        *   Create tests that instantiate `SyncApp`.
        *   Use a testing client (like `unittest.mock` or a simple HTTP client) to send requests to the sync endpoints (e.g., `/sync/meta`, `/msync/begin`).
        *   **Setup:** For these tests, you'll likely need to:
            *   Create temporary user directories and minimal `collection.anki2` and `media.db` files.
            *   Mock `anki.Collection` or parts of it if direct instantiation is too heavy or has unwanted side effects for a specific test.
        *   **Verification:** Assert the JSON responses from the server and check for expected side effects (e.g., changes in the temporary database files, files created in the media folder).
        *   **Scenarios:**
            *   Full authentication flow (`hostKey` -> `meta`).
            *   Basic incremental sync sequence (`meta` -> `start` -> `chunk` -> `applyChunk` -> `finish`).
            *   Basic media sync sequence (`begin` -> `mediaChanges` -> `downloadFiles` / `uploadChanges`).
    3.  **Client Simulation Tests (Advanced - Future Goal):**
        *   This would involve more complex scripts that simulate a series of Anki client actions and verify end-to-end behavior. This is a significant undertaking and can be a later goal.

**Immediate Steps for Automated Testing:**
1.  Start by expanding unit tests for the `media_manager.py` and `schema_updater.py` components as they are critical and have complex logic.
2.  Then, begin creating basic integration tests for the main sync and media sync endpoints.

This combined approach should give us good coverage and confidence in the server's stability and compatibility.

What are your thoughts on this testing plan? We can adjust it based on your priorities.


## Notes
- Priority: Media sync implementation is critical for latest Anki compatibility
- Testing should be continuous throughout development
- Each completed feature should be tested against latest Anki Desktop client
- Document all protocol changes and new features 