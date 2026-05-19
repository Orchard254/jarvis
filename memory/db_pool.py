"""
SQLite connection pool for memory modules.
Thin wrapper around core/thread_db.py — the single source of truth for
SQLite connection management.  Kept for backward-compatible imports.

Previously had its own ConnectionPool class; now delegates to
core.thread_db for thread-per-database connection caching.
"""

import logging
from contextlib import contextmanager
from typing import Optional

from settings import MEMORY_DB
from core.thread_db import get_connection, close_all_connections

logger = logging.getLogger(__name__)


def get_episodic_pool():
    """Return a pool-like object for episodic memory (backward compat)."""
    return _MemoryPoolFacade()


def get_semantic_pool():
    """Return a pool-like object for semantic memory (backward compat)."""
    return _MemoryPoolFacade()


class _MemoryPoolFacade:
    """Duck-typed to match the old ConnectionPool API for backward compat."""

    @contextmanager
    def get_connection(self):
        with connection_context() as conn:
            yield conn

    def close_all(self):
        pass

    def initialize_schema(self, schema_sql: str, indexes: list[str] = None):
        with connection_context() as conn:
            c = conn.cursor()
            c.execute(schema_sql)
            if indexes:
                for idx in indexes:
                    c.execute(idx)
            conn.commit()


@contextmanager
def connection_context():
    """Get a memory DB connection for the current thread."""
    conn = get_connection(MEMORY_DB)
    try:
        yield conn
    finally:
        pass  # connection stays cached in thread-local storage


@contextmanager
def get_episodic_connection():
    """Convenience: get episodic connection (always MEMORY_DB)."""
    with connection_context() as conn:
        yield conn


@contextmanager
def get_semantic_connection():
    """Convenience: get semantic connection (always MEMORY_DB)."""
    with connection_context() as conn:
        yield conn


def shutdown_pools():
    """Close all pooled connections (call on app exit)."""
    close_all_connections()
