"""
SQLite connection pool for memory modules.
Provides thread-safe connection reuse to eliminate connection overhead.
"""

import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from queue import Queue, Empty
from typing import Optional

from settings import MEMORY_DB

logger = logging.getLogger(__name__)


class ConnectionPool:
    """Thread-safe SQLite connection pool with lazy initialization."""
    
    def __init__(self, db_path: Path, pool_size: int = 5, timeout: float = 5.0):
        self.db_path = db_path
        self.pool_size = pool_size
        self.timeout = timeout
        self._pool = Queue(maxsize=pool_size)
        self._lock = threading.Lock()
        self._initialized = False
        self._create_connection = self._make_connection_factory(db_path, timeout)
        self._precreate_connections()
    
    @staticmethod
    def _make_connection_factory(db_path: Path, timeout: float):
        """Create a closure for connection creation to avoid instance method overhead."""
        db_str = str(db_path)
        
        def _create_connection() -> sqlite3.Connection:
            conn = sqlite3.connect(db_str, timeout=timeout, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            # Optimize for write-heavy workloads
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
            return conn
        
        return _create_connection
    
    def _precreate_connections(self):
        """Pre-create all connections in the pool during initialization."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create and validate connections upfront
        for i in range(self.pool_size):
            try:
                conn = self._create_connection()
                # Test the connection
                conn.execute("SELECT 1")
                self._pool.put_nowait(conn)
            except Exception as e:
                logger.warning(f"Failed to pre-create connection {i}: {e}")
                break
        
        if not self._pool.empty():
            self._initialized = True
            logger.info(f"ConnectionPool initialized with {self._pool.qsize()} connections")
    
    @contextmanager
    def get_connection(self):
        """Get a connection from the pool (context manager)."""
        conn = None
        try:
            # Try to get existing connection with timeout
            conn = self._pool.get(timeout=self.timeout)
        except Empty:
            # Pool exhausted, create temporary connection
            logger.debug("Connection pool exhausted, creating temporary connection")
            conn = self._create_connection()
            fresh = False
        else:
            fresh = True
        
        try:
            yield conn
        finally:
            # Return connection to pool if it's healthy and we have space
            if conn and fresh:
                try:
                    self._pool.put_nowait(conn)
                except Exception:
                    # Pool full or error, just close
                    conn.close()
            elif conn:
                conn.close()
    
    def close_all(self):
        """Close all pooled connections (for cleanup)."""
        if not self._pool:
            return
        
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except Empty:
                break
    
    def initialize_schema(self, schema_sql: str, indexes: list[str] = None):
        """Initialize database schema using a pooled connection."""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute(schema_sql)
            if indexes:
                for idx in indexes:
                    c.execute(idx)
            conn.commit()
            logger.info("Database schema initialized")


# Global pools for each database module
_episodic_pool: Optional[ConnectionPool] = None
_semantic_pool: Optional[ConnectionPool] = None


def get_episodic_pool() -> ConnectionPool:
    """Get or create the episodic memory connection pool."""
    global _episodic_pool
    if _episodic_pool is None:
        _episodic_pool = ConnectionPool(MEMORY_DB, pool_size=5)
    return _episodic_pool


def get_semantic_pool() -> ConnectionPool:
    """Get or create the semantic memory connection pool."""
    global _semantic_pool
    if _semantic_pool is None:
        _semantic_pool = ConnectionPool(MEMORY_DB, pool_size=3)
    return _semantic_pool


@contextmanager
def get_episodic_connection():
    """Convenience function: get episodic connection from pool."""
    pool = get_episodic_pool()
    with pool.get_connection() as conn:
        yield conn


@contextmanager
def get_semantic_connection():
    """Convenience function: get semantic connection from pool."""
    pool = get_semantic_pool()
    with pool.get_connection() as conn:
        yield conn
