"""
Per-user sync queue implementation to prevent concurrent syncs for the same user.
"""

import threading
import time
import logging
from typing import Dict, Any, Callable, Optional

logger = logging.getLogger(__name__)


class UserSyncQueue:
    """
    Manages per-user sync locks to ensure only one sync operation per user at a time.
    """
    
    def __init__(self, timeout: int = 300):  # 5 minute timeout
        self.timeout = timeout
        self.user_locks: Dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()
        
    def _get_user_lock(self, username: str) -> threading.Lock:
        """Get or create a lock for the specified user."""
        with self._global_lock:
            if username not in self.user_locks:
                self.user_locks[username] = threading.Lock()
            return self.user_locks[username]
    
    def execute_sync_operation(self, username: str, operation: Callable, *args, **kwargs) -> Any:
        """
        Execute a sync operation for a user, ensuring only one sync per user at a time.
        
        Args:
            username: The user identifier
            operation: The sync operation function to execute
            *args, **kwargs: Arguments to pass to the operation
            
        Returns:
            The result of the operation
            
        Raises:
            TimeoutError: If the operation times out
            Exception: Any exception raised by the operation
        """
        user_lock = self._get_user_lock(username)
        
        # Try to acquire the lock with timeout
        acquired = user_lock.acquire(blocking=False)
        
        if not acquired:
            # If we can't acquire immediately, wait with timeout
            logger.info(f"Lock is busy for user: {username}, waiting...")
            start_wait = time.time()
            while not acquired and (time.time() - start_wait) < self.timeout:
                time.sleep(0.1)  # Small delay to avoid busy waiting
                acquired = user_lock.acquire(blocking=False)
        
        if acquired:
            try:
                logger.info(f"Starting sync operation for user: {username}")
                start_time = time.time()
                
                try:
                    result = operation(*args, **kwargs)
                    elapsed_time = time.time() - start_time
                    logger.info(f"Sync operation completed for user: {username} in {elapsed_time:.2f}s")
                    return result
                    
                except Exception as e:
                    logger.error(f"Sync operation failed for user: {username}: {e}")
                    raise
                    
            finally:
                user_lock.release()
        else:
            logger.error(f"Sync operation timed out waiting for lock for user: {username}")
            raise TimeoutError(f"Sync operation timed out for user: {username}")
    
    def get_queue_status(self, username: str) -> Dict[str, Any]:
        """
        Get the status of a user's sync lock.
        
        Args:
            username: The user identifier
            
        Returns:
            Dictionary containing lock status information
        """
        with self._global_lock:
            has_lock = username in self.user_locks
            is_locked = has_lock and self.user_locks[username].locked()
            
            return {
                'username': username,
                'is_locked': is_locked,
                'has_lock': has_lock
            }
    
    def get_all_queue_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Get the status of all user sync locks.
        
        Returns:
            Dictionary mapping usernames to their lock status
        """
        with self._global_lock:
            status = {}
            for username in self.user_locks.keys():
                status[username] = self.get_queue_status(username)
            return status


# Global instance
_user_sync_queue = None


def get_user_sync_queue(timeout: int = 300) -> UserSyncQueue:
    """
    Get the global user sync queue instance.
    
    Args:
        timeout: Timeout in seconds for sync operations
        
    Returns:
        UserSyncQueue instance
    """
    global _user_sync_queue
    if _user_sync_queue is None:
        _user_sync_queue = UserSyncQueue(timeout=timeout)
    return _user_sync_queue