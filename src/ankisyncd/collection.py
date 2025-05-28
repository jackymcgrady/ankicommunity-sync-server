# -*- coding: utf-8 -*-
# Collection manager for Anki sync server

import os
import logging
from anki.collection import Collection

logger = logging.getLogger("ankisyncd.collection")


class CollectionManager:
    """Manages Anki collection objects for the sync server."""
    
    def __init__(self):
        self._collections = {}
    
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
                Collection(collection_path)
        
        # Return existing collection or create new one
        if collection_path not in self._collections:
            try:
                self._collections[collection_path] = Collection(collection_path)
                logger.info(f"Opened collection: {collection_path}")
            except Exception as e:
                logger.error(f"Error opening collection {collection_path}: {e}")
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