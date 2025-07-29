import os
from sqlite3 import dbapi2 as sqlite
from ankisyncd.sessions.simple_manager import SimpleSessionManager


class SqliteSessionManager(SimpleSessionManager):
    """Stores sessions in a SQLite database to prevent the user from being logged out
    everytime the SyncApp is restarted."""

    def __init__(self, session_db_path):
        super().__init__()

        self.session_db_path = os.path.realpath(session_db_path)
        self._ensure_schema_up_to_date()

    def _ensure_schema_up_to_date(self):
        if not os.path.exists(self.session_db_path):
            return True

        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM sqlite_master "
            "WHERE sql LIKE '%user VARCHAR PRIMARY KEY%' "
            "AND tbl_name = 'session'"
        )
        res = cursor.fetchone()
        conn.close()
        if res is not None:
            raise Exception(
                "Outdated database schema, run utils/migrate_user_tables.py"
            )

    def _conn(self):
        new = not os.path.exists(self.session_db_path)
        conn = sqlite.connect(self.session_db_path)
        if new:
            cursor = conn.cursor()
            cursor.execute(
                "CREATE TABLE session (hkey VARCHAR PRIMARY KEY, skey VARCHAR, username VARCHAR, path VARCHAR, refresh_token VARCHAR, actual_username VARCHAR)"
            )
        else:
            # Check if refresh_token column exists, if not add it
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(session)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'refresh_token' not in columns:
                cursor.execute("ALTER TABLE session ADD COLUMN refresh_token VARCHAR")
                conn.commit()
            if 'actual_username' not in columns:
                cursor.execute("ALTER TABLE session ADD COLUMN actual_username VARCHAR")
                conn.commit()
        return conn

    # Default to using sqlite3 syntax but overridable for sub-classes using other
    # DB API 2 driver variants
    @staticmethod
    def fs(sql):
        return sql

    def load(self, hkey, session_factory=None):
        session = SimpleSessionManager.load(self, hkey)
        if session is not None:
            # Check and refresh Cognito tokens if needed
            if hasattr(self, 'user_manager') and hasattr(self.user_manager, 'refresh_user_session'):
                if not self._validate_and_refresh_token(session.name):
                    # Token refresh failed, invalidate session
                    self.delete(hkey)
                    return None
            return session

        conn = self._conn()
        cursor = conn.cursor()

        cursor.execute(
            self.fs("SELECT skey, username, path, refresh_token, actual_username FROM session WHERE hkey=?"), (hkey,)
        )
        res = cursor.fetchone()

        if res is not None:
            # Check and refresh Cognito tokens if needed
            if hasattr(self, 'user_manager') and hasattr(self.user_manager, 'refresh_user_session'):
                # Get the actual username from stored session or cache
                actual_username = res[4] if len(res) > 4 else self.user_manager.username_cache.get(res[1])
                import logging
                logger = logging.getLogger("ankisyncd")
                logger.debug(f"Loading session for {res[1]}, stored actual username: {res[4] if len(res) > 4 else None}")
                logger.debug(f"Final actual username: {actual_username}")
                if not self._validate_and_refresh_token(res[1], res[3], actual_username):  # Pass actual username
                    # Token refresh failed, remove from database
                    cursor.execute(self.fs("DELETE FROM session WHERE hkey=?"), (hkey,))
                    conn.commit()
                    return None
            
            session = self.sessions[hkey] = session_factory(res[1], res[2])
            session.skey = res[0]
            return session

    def load_from_skey(self, skey, session_factory=None):
        session = SimpleSessionManager.load_from_skey(self, skey)
        if session is not None:
            # Check and refresh Cognito tokens if needed
            if hasattr(self, 'user_manager') and hasattr(self.user_manager, 'refresh_user_session'):
                if not self._validate_and_refresh_token(session.name):
                    # Token refresh failed, invalidate session
                    self.delete_by_skey(skey)
                    return None
            return session

        conn = self._conn()
        cursor = conn.cursor()

        cursor.execute(
            self.fs("SELECT hkey, username, path, refresh_token, actual_username FROM session WHERE skey=?"), (skey,)
        )
        res = cursor.fetchone()

        if res is not None:
            # Check and refresh Cognito tokens if needed
            if hasattr(self, 'user_manager') and hasattr(self.user_manager, 'refresh_user_session'):
                # Get the actual username from stored session or cache
                actual_username = res[4] if len(res) > 4 else self.user_manager.username_cache.get(res[1])
                import logging
                logger = logging.getLogger("ankisyncd")
                logger.debug(f"Loading session for {res[1]}, stored actual username: {res[4] if len(res) > 4 else None}")
                logger.debug(f"Final actual username: {actual_username}")
                if not self._validate_and_refresh_token(res[1], res[3], actual_username):  # Pass actual username
                    # Token refresh failed, remove from database
                    cursor.execute(self.fs("DELETE FROM session WHERE skey=?"), (skey,))
                    conn.commit()
                    return None
            
            session = self.sessions[res[0]] = session_factory(res[1], res[2])
            session.skey = skey
            return session

    def save(self, hkey, session):
        SimpleSessionManager.save(self, hkey, session)

        conn = self._conn()
        cursor = conn.cursor()

        # Get refresh token and actual username from user manager if available
        refresh_token = None
        actual_username = None
        if hasattr(self, 'user_manager') and hasattr(self.user_manager, 'user_session_cache'):
            user_cache = self.user_manager.user_session_cache.get(session.name, {})
            refresh_token = user_cache.get('refresh_token')
        if hasattr(self, 'user_manager') and hasattr(self.user_manager, 'username_cache'):
            actual_username = self.user_manager.username_cache.get(session.name)
        
        cursor.execute(
            "INSERT OR REPLACE INTO session (hkey, skey, username, path, refresh_token, actual_username) VALUES (?, ?, ?, ?, ?, ?)",
            (hkey, session.skey, session.name, session.path, refresh_token, actual_username),
        )

        conn.commit()

    def delete(self, hkey):
        SimpleSessionManager.delete(self, hkey)

        conn = self._conn()
        cursor = conn.cursor()

        cursor.execute(self.fs("DELETE FROM session WHERE hkey=?"), (hkey,))
        conn.commit()

    def delete_by_skey(self, skey):
        """Delete session by session key"""
        # Find hkey first for in-memory cleanup
        for hkey, session in list(self.sessions.items()):
            if session.skey == skey:
                SimpleSessionManager.delete(self, hkey)
                break
        
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(self.fs("DELETE FROM session WHERE skey=?"), (skey,))
        conn.commit()

    def _validate_and_refresh_token(self, username, stored_refresh_token=None, actual_username=None):
        """Validate and refresh Cognito token if needed"""
        try:
            # First check if token is still valid in cache
            if hasattr(self.user_manager, '_is_session_valid'):
                session_cache = getattr(self.user_manager, 'user_session_cache', {})
                if username in session_cache:
                    if self.user_manager._is_session_valid(session_cache[username]):
                        return True
            
            # Token invalid or expired, try to refresh using stored refresh token
            if stored_refresh_token and hasattr(self.user_manager, 'refresh_user_session_with_token'):
                success = self.user_manager.refresh_user_session_with_token(username, stored_refresh_token, actual_username)
                if not success:
                    import logging
                    logger = logging.getLogger("ankisyncd")
                    logger.warning(f"Token refresh failed for {username} with stored token")
                return success
            elif hasattr(self.user_manager, 'refresh_user_session'):
                # Fallback to original method (requires in-memory cache)
                success = self.user_manager.refresh_user_session(username)
                if not success:
                    import logging
                    logger = logging.getLogger("ankisyncd")
                    logger.warning(f"Token refresh failed for {username} with in-memory cache")
                return success
            
            import logging
            logger = logging.getLogger("ankisyncd")
            logger.warning(f"No refresh method available or no stored token for {username}")
            return False
        except Exception as e:
            # Log error but don't crash the session loading
            import logging
            logger = logging.getLogger("ankisyncd")
            logger.error(f"Error validating/refreshing token for {username}: {e}")
            logger.debug(f"Stored refresh token length: {len(stored_refresh_token or '')}")
            logger.debug(f"Actual username: {actual_username}")
            return False
