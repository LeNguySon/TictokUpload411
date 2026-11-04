"""
Unit tests for SQLite Database Connection Manager (PRAGMA WAL, foreign_keys, busy_timeout).
"""

import tempfile
from pathlib import Path

import pytest
from src.infrastructure.database.connection import (
    db_session,
    get_db_connection,
)


def test_sqlite_pragmas_configured():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test.db"
        conn = get_db_connection(db_path)
        try:
            # 1. Foreign keys must be ON
            fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
            assert fk == 1, "PRAGMA foreign_keys must be ON (1)"

            # 2. Journal mode must be WAL
            jm = conn.execute("PRAGMA journal_mode;").fetchone()[0]
            assert jm.lower() == "wal", f"PRAGMA journal_mode must be WAL, got {jm}"

            # 3. Synchronous mode must be NORMAL (1)
            sync = conn.execute("PRAGMA synchronous;").fetchone()[0]
            assert sync == 1, "PRAGMA synchronous must be NORMAL (1)"

            # 4. Busy timeout must be at least 10000ms
            bt = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
            assert bt >= 10000, f"PRAGMA busy_timeout must be >= 10000ms, got {bt}"

            # 5. Row factory must return dictionary-accessible rows
            conn.execute("CREATE TABLE dummy (id INTEGER PRIMARY KEY, val TEXT);")
            conn.execute("INSERT INTO dummy (val) VALUES ('hello');")
            row = conn.execute("SELECT * FROM dummy WHERE id=1;").fetchone()
            assert row["val"] == "hello"
        finally:
            conn.close()


def test_db_session_commit_and_rollback():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_tx.db"

        # Initialize test table
        with db_session(db_path) as conn:
            conn.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT);")
            conn.execute("INSERT INTO accounts (name) VALUES ('alice');")

        # Verify commit succeeded
        with db_session(db_path, write=False) as conn:
            count = conn.execute("SELECT COUNT(*) FROM accounts;").fetchone()[0]
            assert count == 1

        # Verify rollback on exception
        with pytest.raises(ValueError):
            with db_session(db_path) as conn:
                conn.execute("INSERT INTO accounts (name) VALUES ('bob');")
                raise ValueError("Simulated business error")

        # Verify 'bob' was rolled back
        with db_session(db_path, write=False) as conn:
            count = conn.execute("SELECT COUNT(*) FROM accounts;").fetchone()[0]
            assert count == 1
            names = [r[0] for r in conn.execute("SELECT name FROM accounts;").fetchall()]
            assert names == ["alice"]
