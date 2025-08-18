import os
import psycopg2
from psycopg2.extras import RealDictCursor
from ankisyncd import logging

logger = logging.get_logger(__name__)


class DatabaseManager:
    """Manages PostgreSQL database connections and user profile operations."""
    
    def __init__(self):
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'postgres'),
            'port': os.getenv('POSTGRES_PORT', '5432'),
            'database': os.getenv('POSTGRES_DB', 'ankipi'),
            'user': os.getenv('POSTGRES_USER', 'ankipi'),
            'password': os.getenv('POSTGRES_PASSWORD')
        }
        
        if not self.db_config['password']:
            raise ValueError("POSTGRES_PASSWORD environment variable is required")
    
    def get_connection(self):
        """Get a database connection."""
        try:
            conn = psycopg2.connect(**self.db_config)
            return conn
        except psycopg2.Error as e:
            logger.error(f"Database connection failed: {e}")
            raise
    
    def create_user_profile(self, uuid, name):
        """Create a new user profile."""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        INSERT INTO profiles (uuid, name, is_active) 
                        VALUES (%s, %s, %s)
                        ON CONFLICT (uuid) DO UPDATE SET
                            name = EXCLUDED.name
                        RETURNING profile_id, uuid, name, created_at, is_active
                    """, (uuid, name, True))
                    
                    result = cur.fetchone()
                    conn.commit()
                    logger.info(f"Created/updated user profile for UUID {uuid}, name {name}")
                    return dict(result)
        except psycopg2.Error as e:
            logger.error(f"Failed to create user profile for UUID {uuid}: {e}")
            raise
    
    def get_user_profile_by_uuid(self, uuid):
        """Get user profile by UUID."""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT profile_id, uuid, name, created_at, is_active
                        FROM profiles 
                        WHERE uuid = %s
                    """, (uuid,))
                    
                    result = cur.fetchone()
                    return dict(result) if result else None
        except psycopg2.Error as e:
            logger.error(f"Failed to get user profile for UUID {uuid}: {e}")
            raise
    
    def get_user_profile_by_name(self, name):
        """Get user profile by name."""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT profile_id, uuid, name, created_at, is_active
                        FROM profiles 
                        WHERE name = %s
                    """, (name,))
                    
                    result = cur.fetchone()
                    return dict(result) if result else None
        except psycopg2.Error as e:
            logger.error(f"Failed to get user profile for name {name}: {e}")
            raise
    
    def update_user_active_status(self, uuid, is_active):
        """Update user active status."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE profiles 
                        SET is_active = %s
                        WHERE uuid = %s
                    """, (is_active, uuid))
                    
                    conn.commit()
                    logger.info(f"Updated active status for UUID {uuid} to {is_active}")
                    return cur.rowcount > 0
        except psycopg2.Error as e:
            logger.error(f"Failed to update active status for UUID {uuid}: {e}")
            raise