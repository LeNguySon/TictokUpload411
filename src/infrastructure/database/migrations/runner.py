"""
Database Migration Runner for SQLite (Applies 24 schemas and seeds system defaults).
Clean Architecture: Infrastructure Layer.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.infrastructure.database.connection import DEFAULT_DB_PATH, db_session
from src.infrastructure.database.migrations.schemas import DDL_BASE_SCHEMAS

logger = logging.getLogger(__name__)


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
            if "session_expires_at" not in prof_cols:
                conn.execute("ALTER TABLE profiles ADD COLUMN session_expires_at REAL DEFAULT NULL;")
            if "cookies_synced_at" not in prof_cols:
                conn.execute("ALTER TABLE profiles ADD COLUMN cookies_synced_at TEXT DEFAULT NULL;")
            if "api_reconnect_required" not in prof_cols:
                conn.execute("ALTER TABLE profiles ADD COLUMN api_reconnect_required INTEGER DEFAULT 0;")
            if "traffic_source_json" not in prof_cols:
                conn.execute("ALTER TABLE profiles ADD COLUMN traffic_source_json TEXT DEFAULT NULL;")
            if "optimal_hour" not in prof_cols:
                conn.execute("ALTER TABLE profiles ADD COLUMN optimal_hour INTEGER DEFAULT 12;")
            if "retention_stats_json" not in prof_cols:
                conn.execute("ALTER TABLE profiles ADD COLUMN retention_stats_json TEXT DEFAULT NULL;")
            if "fingerprint_json" not in prof_cols:
                conn.execute("ALTER TABLE profiles ADD COLUMN fingerprint_json TEXT DEFAULT NULL;")
            if "audience_demographics_json" not in prof_cols:
                conn.execute("ALTER TABLE profiles ADD COLUMN audience_demographics_json TEXT DEFAULT NULL;")
            if "optimal_posting_hours_json" not in prof_cols:
                conn.execute("ALTER TABLE profiles ADD COLUMN optimal_posting_hours_json TEXT DEFAULT NULL;")
            if "competitor_intelligence_json" not in prof_cols:
                conn.execute("ALTER TABLE profiles ADD COLUMN competitor_intelligence_json TEXT DEFAULT NULL;")
            if "publish_settings_json" not in prof_cols:
                conn.execute("ALTER TABLE profiles ADD COLUMN publish_settings_json TEXT DEFAULT NULL;")

        # Pre-migration: check if videoTables exists and needs deep analytics columns
        vt_info = conn.execute("PRAGMA table_info(videoTables);").fetchall()
        vt_cols = [r[1] for r in vt_info]
        if vt_cols:
            if "search_terms_json" not in vt_cols:
                conn.execute("ALTER TABLE videoTables ADD COLUMN search_terms_json TEXT DEFAULT NULL;")
            if "traffic_sources_json" not in vt_cols:
                conn.execute("ALTER TABLE videoTables ADD COLUMN traffic_sources_json TEXT DEFAULT NULL;")
            if "retention_points_json" not in vt_cols:
                conn.execute("ALTER TABLE videoTables ADD COLUMN retention_points_json TEXT DEFAULT NULL;")
            if "finish_rate" not in vt_cols:
                conn.execute("ALTER TABLE videoTables ADD COLUMN finish_rate REAL DEFAULT 0.0;")
            if "viewer_locations_json" not in vt_cols:
                conn.execute("ALTER TABLE videoTables ADD COLUMN viewer_locations_json TEXT DEFAULT NULL;")
            if "ai_comments_json" not in vt_cols:
                conn.execute("ALTER TABLE videoTables ADD COLUMN ai_comments_json TEXT DEFAULT NULL;")

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

    protect_plaintext_secrets(path)
    return get_database_tables(path)


def protect_plaintext_secrets(db_path: Path | str, backup_dir: Path | str | None = None) -> dict[str, int]:
    """DPAPI-protects secret values still stored as plaintext (written before field_crypto existed).

    Idempotent: only non-empty values without the ``dpapi:v1:`` prefix are touched. When there is something
    to migrate, the database is first copied to ``backup_dir`` (default: next to it). That copy still holds
    the plaintext secrets: delete it once the app is confirmed to work. Returns updated values per table.
    """
    import sqlite3
    import time

    from src.infrastructure.credentials.field_crypto import PREFIX, SENSITIVE_COLUMNS, protect

    path = Path(db_path)
    pending: dict[str, list[str]] = {}
    with db_session(path, write=False) as conn:
        for table in ("profiles", "proxies"):
            cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table});").fetchall()]
            secret_cols = [c for c in cols if c in SENSITIVE_COLUMNS]
            todo = [
                c
                for c in secret_cols
                if conn.execute(
                    f"SELECT 1 FROM {table} WHERE {c} IS NOT NULL AND {c} <> '' AND {c} NOT LIKE ? LIMIT 1;",
                    (PREFIX + "%",),
                ).fetchone()
            ]
            pending[table] = todo
    counts = {"profiles": 0, "proxies": 0}
    if not any(pending.values()):
        return counts

    target = Path(backup_dir) if backup_dir else path.parent
    target.mkdir(parents=True, exist_ok=True)
    backup = target / f"{path.stem}_before_secret_encryption_{time.strftime('%Y%m%d_%H%M%S')}.db"
    src_con, dst_con = sqlite3.connect(path), sqlite3.connect(backup)
    try:
        src_con.backup(dst_con)
    finally:
        src_con.close()
        dst_con.close()
    logger.warning("Plaintext secrets found: database backed up to %s before encryption (delete it later)", backup)

    with db_session(path) as conn:
        for table, cols in pending.items():
            for col in cols:
                rows = conn.execute(
                    f"SELECT id, {col} FROM {table} WHERE {col} IS NOT NULL AND {col} <> '' AND {col} NOT LIKE ?;",
                    (PREFIX + "%",),
                ).fetchall()
                for row in rows:
                    conn.execute(f"UPDATE {table} SET {col} = ? WHERE id = ?;", (protect(row[1]), row[0]))
                counts[table] += len(rows)
    logger.info("Protected %d profile and %d proxy secret values with DPAPI", counts["profiles"], counts["proxies"])
    return counts


def get_database_tables(db_path: Path | str | None = None) -> list[str]:
    """Returns sorted list of user tables in the SQLite database."""
    path = db_path or DEFAULT_DB_PATH
    with db_session(path, write=False) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
        ).fetchall()
        return [row[0] for row in rows]
