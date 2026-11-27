from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from infra.database.connection import get_connection, get_db_context


def test_get_connection_enforces_pragmas(tmp_path: Path) -> None:
    """Verify foreign keys and row factory are enabled on connection."""
    db_file: Path = tmp_path / "test.db"
    conn: sqlite3.Connection = get_connection(db_file)
    try:
        cursor: sqlite3.Cursor = conn.execute("PRAGMA foreign_keys;")
        fk_status: int = cursor.fetchone()[0]
        assert fk_status == 1
        assert conn.row_factory == sqlite3.Row
    finally:
        conn.close()


def test_get_db_context_transaction_commit(tmp_path: Path) -> None:
    """Verify transactions are committed automatically upon context exit."""
    db_file: Path = tmp_path / "test.db"
    with get_db_context(db_file) as conn:
        conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, name TEXT);")
        conn.execute("INSERT INTO sample (name) VALUES (?);", ("test_entry",))

    with get_db_context(db_file) as conn:
        row: sqlite3.Row = conn.execute("SELECT name FROM sample WHERE id = 1;").fetchone()
        assert row["name"] == "test_entry"


def test_get_db_context_transaction_rollback(tmp_path: Path) -> None:
    """Verify transactions rollback on unexpected exceptions."""
    db_file: Path = tmp_path / "test.db"
    with get_db_context(db_file) as conn:
        conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, val TEXT);")

    with pytest.raises(RuntimeError), get_db_context(db_file) as conn:
        conn.execute("INSERT INTO sample (id, val) VALUES (1, 'initial');")
        raise RuntimeError("Forced abort")

    with get_db_context(db_file) as conn:
        count: int = conn.execute("SELECT count(*) FROM sample;").fetchone()[0]
        assert count == 0
