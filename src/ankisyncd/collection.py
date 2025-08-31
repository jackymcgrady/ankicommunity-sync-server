# -*- coding: utf-8 -*-
# Collection manager for Anki sync server

import os
import logging
import glob
from contextlib import contextmanager
from anki.collection import Collection

logger = logging.getLogger("ankisyncd.collection")


class CollectionManager:
    """Manages Anki collection objects for the sync server."""
    
    def __init__(self):
        self._collections = {}
        self._cleanup_nfs_locks_on_startup()
    
    def get_collection(self, collection_path, setup_new_collection=None):
        """
        Get or create a collection object for the given path.
        
        Args:
            collection_path: Path to the collection.anki2 file
            setup_new_collection: Optional function to set up new collections
            
        Returns:
            Collection object
        """
        # Ensure the directory exists
        collection_dir = os.path.dirname(collection_path)
        os.makedirs(collection_dir, exist_ok=True)
        
        # Check if collection file exists
        if not os.path.exists(collection_path):
            if setup_new_collection:
                setup_new_collection(collection_path)
            else:
                # Create a new empty collection
                Collection(collection_path, server=True)
        
        # Clean up any NFS locks before opening
        self.cleanup_nfs_locks(collection_dir)
        
        # Return existing collection or create new one
        if collection_path not in self._collections:
            try:
                self._collections[collection_path] = Collection(collection_path, server=True)
                logger.info(f"Opened collection: {collection_path}")
            except Exception as e:
                logger.error(f"Error opening collection {collection_path}: {e}")
                # Try cleaning up locks and retry once
                self.cleanup_nfs_locks(collection_dir)
                raise
        
        return self._collections[collection_path]
    
    def close_collection(self, collection_path):
        """Close a collection and remove it from cache."""
        if collection_path in self._collections:
            try:
                self._collections[collection_path].close()
                del self._collections[collection_path]
                logger.info(f"Closed collection: {collection_path}")
            except Exception as e:
                logger.error(f"Error closing collection {collection_path}: {e}")
    
    def close_all(self):
        """Close all open collections."""
        for path in list(self._collections.keys()):
            self.close_collection(path)
    
    def cleanup_nfs_locks(self, collection_dir):
        """Remove NFS lock files that prevent collection access."""
        try:
            nfs_files = glob.glob(os.path.join(collection_dir, '.nfs*'))
            for nfs_file in nfs_files:
                try:
                    os.remove(nfs_file)
                    logger.info(f"Cleaned up NFS lock file: {os.path.basename(nfs_file)}")
                except OSError as e:
                    logger.warning(f"Could not remove NFS lock file {nfs_file}: {e}")
        except Exception as e:
            logger.error(f"Error during NFS lock cleanup in {collection_dir}: {e}")
    
    def _cleanup_nfs_locks_on_startup(self):
        """Clean up NFS lock files on startup for all collection directories."""
        collections_root = os.environ.get('COLLECTIONS_ROOT', '/data/collections')
        if os.path.exists(collections_root):
            for user_dir in os.listdir(collections_root):
                collection_dir = os.path.join(collections_root, user_dir)
                if os.path.isdir(collection_dir):
                    self.cleanup_nfs_locks(collection_dir)
    
    @contextmanager
    def get_collection_context(self, collection_path, setup_new_collection=None):
        """Context manager for safe collection access."""
        # Clean up any NFS locks before opening
        collection_dir = os.path.dirname(collection_path)
        self.cleanup_nfs_locks(collection_dir)
        
        collection = self.get_collection(collection_path, setup_new_collection)
        try:
            yield collection
        finally:
            # Ensure proper cleanup without full close
            if collection_path in self._collections:
                try:
                    collection.db.commit()
                except Exception as e:
                    logger.warning(f"Error committing collection {collection_path}: {e}")
    
    def __del__(self):
        """Ensure collections are closed on deletion."""
        if hasattr(self, '_collections'):
            self.close_all() 