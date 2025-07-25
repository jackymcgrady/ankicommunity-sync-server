import os
import anki.storage

import ankisyncd.media


class CollectionWrapper:
    """A simple wrapper around an anki.storage.Collection object.

    This allows us to manage and refer to the collection, whether it's open or not. It
    also provides a special "continuation passing" interface for executing functions
    on the collection, which makes it easy to switch to a threading mode.

    See ThreadingCollectionWrapper for a version that maintains a seperate thread for
    interacting with the collection.
    """

    def __init__(self, _config, path, setup_new_collection=None):
        self.path = os.path.realpath(path)
        self.username = os.path.basename(os.path.dirname(self.path))
        self.setup_new_collection = setup_new_collection
        self.db = None
        self.__col = None

    def __del__(self):
        """Close the collection if the user forgot to do so."""
        self.close()

    def execute(self, func, args=[], kw={}, waitForReturn=True):
        """Executes the given function with the underlying anki.storage.Collection
        object as the first argument and any additional arguments specified by *args
        and **kw.

        If 'waitForReturn' is True, then it will block until the function has
        executed and return its return value.  If False, the function MAY be
        executed some time later and None will be returned.
        """

        # Open the collection and execute the function
        self.open()
        args = [self.__col] + args
        ret = func(*args, **kw)

        # Re-assign the db object, in case it was re-opened
        self.db = self.__col.db

        # Only return the value if they requested it, so the interface remains
        # identical between this class and ThreadingCollectionWrapper
        if waitForReturn:
            return ret

    def __create_collection(self):
        """Creates a new collection and runs any special setup."""

        # mkdir -p the path, because it might not exist
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

        col = self._get_collection()

        # Do any special setup
        if self.setup_new_collection is not None:
            self.setup_new_collection(col)

        return col

    def _get_collection(self):
        col = anki.storage.Collection(self.path, server=True)

        # Ugly hack, replace default media manager with our custom one
        # Check if media manager has close method before calling it
        if hasattr(col.media, 'close'):
            col.media.close()
        col.media = ankisyncd.media.ServerMediaManager(col)

        return col

    def open(self):
        """Open the collection, or create it if it doesn't exist."""
        if self.__col is None:
            if os.path.exists(self.path):
                self.__col = self._get_collection()
            else:
                self.__col = self.__create_collection()

    def close(self):
        """Close the collection if opened."""
        if not self.opened():
            return

        # Force WAL checkpoint to commit changes to main database file
        # This ensures the collection.anki2 file contains all changes
        try:
            if hasattr(self.__col, '_db') and self.__col._db:
                self.__col._db.execute("PRAGMA wal_checkpoint(FULL)")
                self.__col._db.commit()
        except Exception as e:
            # Log but don't fail if checkpoint fails
            import logging
            logging.warning(f"WAL checkpoint failed: {e}")

        self.__col.close()
        self.db = None
        self.__col = None

    def opened(self):
        """Returns True if the collection is open, False otherwise."""
        return self.__col is not None
