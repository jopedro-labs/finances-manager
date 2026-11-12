"""
SQLite database connection management and transactional context handling.
Provides robust context-managed database connections with foreign key enforcement
and concurrency timeout configurations.
"""

from __future__ import annotations

__all__ = ["DEFAULT_DB_PATH", "get_connection", "get_db_context"]

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from config import get_settings

DEFAULT_CONNECT_TIMEOUT_SEC: float = 10.0
DEFAULT_DB_PATH: Path = get_settings().finance_db_file


def _resolve_db_path(db_path: Path | str | None) -> Path:
    """Resolves the database path, falling back to settings lazily if None."""
    if db_path is not None:
        return Path(db_path)
    return get_settings().finance_db_file


def get_connection(
    db_path: Path | str | None = None,
    timeout: float = DEFAULT_CONNECT_TIMEOUT_SEC,
) -> sqlite3.Connection:
    """Establishes and returns a SQLite database connection configured with row factory,
    foreign key enforcement, and a safety concurrency timeout.

    Args:
        db_path: Path to the target SQLite database file. Defaults to settings value if None.
        timeout: Maximum number of seconds to wait for database locks to clear.

    Returns:
        An active sqlite3.Connection instance with foreign keys enabled and Row factory set.

    Raises:
        sqlite3.OperationalError: If the database cannot be accessed or locked within the timeout window.
    """
    target_path: Path = _resolve_db_path(db_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    conn: sqlite3.Connection = sqlite3.connect(target_path, timeout=timeout)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def get_db_context(
    db_path: Path | str | None = None,
    timeout: float = DEFAULT_CONNECT_TIMEOUT_SEC,
) -> Generator[sqlite3.Connection, None, None]:
    """Context manager providing transactional SQLite connection handling.
    Automatically commits changes on successful execution or rolls back on exception,
    guaranteeing connection closure in all scenarios. Note: DDL statements (CREATE TABLE,
    ALTER TABLE) committed mid-context cannot be rolled back by this manager on failure.

    Args:
        db_path: Path to the target SQLite database file. Defaults to settings value if None.
        timeout: Maximum number of seconds to wait for database locks to clear.

    Yields:
        An active sqlite3.Connection instance within an active transaction.

    Raises:
        Exception: Re-raises any exception encountered during the transactional block after rolling back.
    """
    conn: sqlite3.Connection = get_connection(db_path, timeout=timeout)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()