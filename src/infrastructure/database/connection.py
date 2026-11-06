"""
SQLite Database Connection Manager with PRAGMA WAL, foreign keys, and thread-safe sessions.
Clean Architecture: Infrastructure Layer.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("data/app.db")

_WRITER_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def writer_lock(db_path: Path | str | None = None) -> threading.RLock:
    """Serialize writers per database path; concurrent readers remain independent."""
    key = str(Path(db_path or DEFAULT_DB_PATH).resolve()).casefold()
    with _LOCKS_GUARD:
        return _WRITER_LOCKS.setdefault(key, threading.RLock())


def get_db_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Creates and configures an optimized SQLite connection:
    - WAL journal mode
    - foreign_keys enabled
    - busy_timeout 10,000 ms
    - synchronous = NORMAL
    - cache_size = 64MB (-64000)
    - temp_store = MEMORY
    - sqlite3.Row row factory
    """
    path = Path(db_path or DEFAULT_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        str(path),
        timeout=10.0,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row

    # Execute performance and integrity PRAGMAs
    conn.execute("PRAGMA busy_timeout = 10000;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA cache_size = -64000;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    conn.execute("PRAGMA secure_delete = ON;")

    return conn


@contextmanager
def db_session(db_path: Path | str | None = None, *, write: bool = True) -> Generator[sqlite3.Connection, None, None]:
    """Transaction context manager with coordinated write serialization and retries."""
    lock = writer_lock(db_path) if write else None
    if lock is not None:
        lock.acquire()

    conn: sqlite3.Connection | None = None
    try:
        for attempt in range(10):
            try:
                conn = get_db_connection(db_path)
                if write:
                    conn.execute("BEGIN IMMEDIATE")
                else:
                    conn.execute("PRAGMA query_only = ON")
                break
            except sqlite3.OperationalError as exc:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception as ignored:
                        logger.debug("db_session: ignored error: %s", ignored)
                    conn = None
                if "locked" not in str(exc).lower() or attempt == 9:
                    raise
                time.sleep(min(0.025 * (1.5**attempt), 0.5))

        if conn is None:
            raise sqlite3.OperationalError("Could not establish database connection.")

        yield conn

        if write and conn is not None:
            conn.commit()
    except Exception:
        if conn is not None and write:
            try:
                conn.rollback()
            except Exception as ignored:
                logger.debug("db_session: ignored error: %s", ignored)
        raise
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception as ignored:
                logger.debug("db_session: ignored error: %s", ignored)
        if lock is not None:
            lock.release()
