"""
Thread-local SQLite connection management.

Provides thread-safe connection handling to prevent "SQLite objects created in
a thread can only be used in that same thread" errors.

Usage:
    from core.thread_db import get_connection, close_thread_connections
    
    # In any thread:
    with get_connection(MEMORY_DB) as conn:
        conn.execute("SELECT 1")
    
    # On thread exit (optional cleanup):
    close_thread_connections()
"""

import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Thread-local storage for connections
_thread_local = threading.local()


def _get_thread_connections() -> dict:
    """Get or create the connection dict for the current thread."""
    if not hasattr(_thread_local, 'connections'):
        _thread_local.connections = {}
    return _thread_local.connections


def get_connection(db_path: Path, timeout: float = 5.0) -> sqlite3.Connection:
    """
    Get or create a SQLite connection for the current thread.
    
    Each thread gets its own connection to avoid thread-safety issues.
    Connections are cached per-thread for reuse.
    
    Args:
        db_path: Path to the SQLite database
        timeout: Busy timeout in seconds
        
    Returns:
        sqlite3.Connection configured for the current thread
    """
    connections = _get_thread_connections()
    db_key = str(db_path.resolve())
    
    if db_key not in connections:
        logger.debug(f"Creating new SQLite connection for thread {threading.current_thread().ident}")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_key, timeout=timeout)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(f"PRAGMA busy_timeout={int(timeout * 1000)}")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
        connections[db_key] = conn
    
    return connections[db_key]


@contextmanager
def connection_context(db_path: Path, timeout: float = 5.0):
    """
    Context manager for thread-safe SQLite connections.
    
    Usage:
        with connection_context(MEMORY_DB) as conn:
            conn.execute("SELECT 1")
    
    The connection is returned to the thread's cache (not closed) for reuse.
    """
    conn = get_connection(db_path, timeout)
    try:
        yield conn
    finally:
        # Connection stays cached in thread for reuse
        pass


def close_thread_connections():
    """
    Close all SQLite connections for the current thread.
    
    Call this when a thread is exiting to release resources.
    """
    connections = _get_thread_connections()
    for db_key, conn in list(connections.items()):
        try:
            logger.debug(f"Closing SQLite connection for {db_key} in thread {threading.current_thread().ident}")
            conn.close()
        except Exception as e:
            logger.warning(f"Error closing connection {db_key}: {e}")
    connections.clear()


def close_all_connections():
    """
    Close all SQLite connections across all threads.
    
    Use with caution - only call during shutdown.
    """
    # Note: This only closes connections accessible from the current thread's view
    # For proper multi-thread cleanup, each thread should call close_thread_connections()
    close_thread_connections()


# Convenience functions for common databases
def get_memory_connection(timeout: float = 5.0):
    """Get a connection to MEMORY_DB for the current thread."""
    from settings import MEMORY_DB
    return get_connection(MEMORY_DB, timeout)


def get_pc_index_connection(timeout: float = 5.0):
    """Get a connection to PC_INDEX_DB for the current thread."""
    from settings import PC_INDEX_DB
    return get_connection(PC_INDEX_DB, timeout)


def get_skills_connection(timeout: float = 5.0):
    """Get a connection to SKILLS_DB for the current thread."""
    from settings import SKILLS_DB
    return get_connection(SKILLS_DB, timeout)
