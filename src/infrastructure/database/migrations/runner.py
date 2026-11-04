"""
Database Migration Runner for SQLite (Applies 24 schemas and seeds system defaults).
Clean Architecture: Infrastructure Layer.
"""

from __future__ import annotations

from pathlib import Path

from src.infrastructure.database.connection import DEFAULT_DB_PATH, db_session
from src.infrastructure.database.migrations.schemas import DDL_BASE_SCHEMAS


def run_all_migrations(db_path: Path | str | None = None) -> list[str]:
    """Applies all foundational schemas and ensures default project exists.
    Returns list of table names present in the database.
    """
    path = db_path or DEFAULT_DB_PATH
    with db_session(path) as conn:
        conn.executescript(DDL_BASE_SCHEMAS)

        # Ensure default project exists
        cur = conn.execute("SELECT COUNT(*) FROM projects WHERE id = 1;")
        if cur.fetchone()[0] == 0:
            conn.execute(
                """
                INSERT OR IGNORE INTO projects (id, name, description, color)
                VALUES (1, 'Dự án mặc định', 'Nhóm mặc định chứa các hồ sơ chưa phân loại', '#0078D4');
                """
            )

    return get_database_tables(path)


def get_database_tables(db_path: Path | str | None = None) -> list[str]:
    """Returns sorted list of user tables in the SQLite database."""
    path = db_path or DEFAULT_DB_PATH
    with db_session(path, write=False) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
        ).fetchall()
        return [row[0] for row in rows]
