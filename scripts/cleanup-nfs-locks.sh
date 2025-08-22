#!/bin/bash
# cleanup-nfs-locks.sh
# Script to clean up NFS lock files that prevent collection access

COLLECTIONS_ROOT="${COLLECTIONS_ROOT:-/data/collections}"
LOG_PREFIX="[NFS-Cleanup]"

# Function to log messages
log_info() {
    echo "$LOG_PREFIX $(date): $1"
}

log_error() {
    echo "$LOG_PREFIX ERROR $(date): $1" >&2
}

# Main cleanup function
cleanup_nfs_locks() {
    if [ ! -d "$COLLECTIONS_ROOT" ]; then
        log_error "Collections root directory not found: $COLLECTIONS_ROOT"
        return 1
    fi

    local total_cleaned=0
    
    # Find all .nfs* files in collection directories
    while IFS= read -r -d '' nfs_file; do
        if rm -f "$nfs_file" 2>/dev/null; then
            log_info "Removed NFS lock file: $(basename "$nfs_file") from $(dirname "$nfs_file")"
            ((total_cleaned++))
        else
            log_error "Failed to remove NFS lock file: $nfs_file"
        fi
    done < <(find "$COLLECTIONS_ROOT" -name ".nfs*" -type f -print0 2>/dev/null)

    # Also clean up any stale WAL files
    while IFS= read -r -d '' wal_file; do
        if rm -f "$wal_file" 2>/dev/null; then
            log_info "Removed stale WAL file: $(basename "$wal_file") from $(dirname "$wal_file")"
            ((total_cleaned++))
        fi
    done < <(find "$COLLECTIONS_ROOT" -name "*.anki2-wal" -o -name "*-shm" -o -name "*-wal" | grep -v "journal" | head -20 | tr '\n' '\0' 2>/dev/null)

    if [ $total_cleaned -eq 0 ]; then
        log_info "No lock files found to clean up"
    else
        log_info "Successfully cleaned up $total_cleaned lock files"
    fi
}

# Run cleanup
cleanup_nfs_locks