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
        # Pre-migration: check if video_registry exists and needs schedule_time before creating indices
        vr_info = conn.execute("PRAGMA table_info(video_registry);").fetchall()
        vr_cols = [r[1] for r in vr_info]
        if vr_cols and "schedule_time" not in vr_cols:
            conn.execute("ALTER TABLE video_registry ADD COLUMN schedule_time TEXT DEFAULT NULL;")
        if vr_cols and "error_message" not in vr_cols:
            # Reason of the last failed upload (redacted, truncated) - survives table reloads.
            conn.execute("ALTER TABLE video_registry ADD COLUMN error_message TEXT DEFAULT NULL;")

        # Pre-migration: check if projects exists and needs video_folder
        proj_info = conn.execute("PRAGMA table_info(projects);").fetchall()
        proj_cols = [r[1] for r in proj_info]
        if proj_cols and "video_folder" not in proj_cols:
            conn.execute("ALTER TABLE projects ADD COLUMN video_folder TEXT DEFAULT NULL;")

        # Pre-migration: check if profiles exists and needs refresh_token, client_id, cookie_email
        prof_info = conn.execute("PRAGMA table_info(profiles);").fetchall()
        prof_cols = [r[1] for r in prof_info]
        if prof_cols:
            if "refresh_token" not in prof_cols:
                conn.execute("ALTER TABLE profiles ADD COLUMN refresh_token TEXT DEFAULT NULL;")
            if "client_id" not in prof_cols:
                conn.execute("ALTER TABLE profiles ADD COLUMN client_id TEXT DEFAULT NULL;")
            if "cookie_email" not in prof_cols:
                conn.execute("ALTER TABLE profiles ADD COLUMN cookie_email TEXT DEFAULT NULL;")
            if "direct_connection" not in prof_cols:
                conn.execute("ALTER TABLE profiles ADD COLUMN direct_connection INTEGER DEFAULT 0;")

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

        # Ensure index exists
        conn.execute("CREATE INDEX IF NOT EXISTS idx_video_registry_schedule ON video_registry(status, schedule_time);")

    return get_database_tables(path)


def get_database_tables(db_path: Path | str | None = None) -> list[str]:
    """Returns sorted list of user tables in the SQLite database."""
    path = db_path or DEFAULT_DB_PATH
    with db_session(path, write=False) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
        ).fetchall()
        return [row[0] for row in rows]
