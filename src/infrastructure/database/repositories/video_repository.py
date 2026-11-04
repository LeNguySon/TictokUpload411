"""
Video Repository: Manages local video assets, SHA-256 deduplication, and atomic reservation.
Clean Architecture: Infrastructure Layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.infrastructure.database.connection import DEFAULT_DB_PATH, db_session


class VideoRepository:
    """Repository for managing the `video_registry` table."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH

    def register_or_update(
        self,
        video_hash: str,
        file_path: str,
        file_name: str,
        file_size: int,
        mtime: float,
    ) -> int:
        """Registers a new video file or updates metadata if already tracked."""
        with db_session(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO video_registry (
                    video_hash, file_path, file_name, file_size, mtime, status
                ) VALUES (?, ?, ?, ?, ?, 'available')
                ON CONFLICT(video_hash) DO UPDATE SET
                    file_path = excluded.file_path,
                    file_name = excluded.file_name,
                    file_size = excluded.file_size,
                    mtime = excluded.mtime,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                (video_hash, file_path, file_name, file_size, mtime),
            )
            # Retrieve row id
            row = conn.execute("SELECT id FROM video_registry WHERE video_hash = ?;", (video_hash,)).fetchone()
            return int(row[0])

    def get_by_id(self, video_id: int) -> dict[str, Any] | None:
        with db_session(self.db_path, write=False) as conn:
            row = conn.execute("SELECT * FROM video_registry WHERE id = ?;", (video_id,)).fetchone()
            return dict(row) if row else None

    def get_by_hash(self, video_hash: str) -> dict[str, Any] | None:
        with db_session(self.db_path, write=False) as conn:
            row = conn.execute("SELECT * FROM video_registry WHERE video_hash = ?;", (video_hash,)).fetchone()
            return dict(row) if row else None

    def try_reserve(self, video_id: int, assigned_profile_id: int) -> bool:
        """Atomic reservation: locks an available video to a specific profile.
        Fails if already reserved, uploading, or published.
        """
        with db_session(self.db_path) as conn:
            cur = conn.execute(
                """
                UPDATE video_registry
                SET status = 'reserved', assigned_profile_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'available';
                """,
                (assigned_profile_id, video_id),
            )
            return cur.rowcount > 0

    def release_reservation(self, video_id: int) -> bool:
        """Releases a reserved video back to 'available' pool."""
        with db_session(self.db_path) as conn:
            cur = conn.execute(
                """
                UPDATE video_registry
                SET status = 'available', assigned_profile_id = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'reserved';
                """,
                (video_id,),
            )
            return cur.rowcount > 0

    def mark_published(
        self,
        video_id: int,
        published_profile_id: int,
        tiktok_video_id: str,
    ) -> bool:
        """Marks video as permanently published to avoid duplicate uploads."""
        with db_session(self.db_path) as conn:
            cur = conn.execute(
                """
                UPDATE video_registry
                SET status = 'published',
                    published_profile_id = ?,
                    tiktok_video_id = ?,
                    published_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?;
                """,
                (published_profile_id, tiktok_video_id, video_id),
            )
            return cur.rowcount > 0

    def mark_error(self, video_id: int, error_message: str | None = None) -> bool:
        """Marks video as failed and increments retry count."""
        with db_session(self.db_path) as conn:
            cur = conn.execute(
                """
                UPDATE video_registry
                SET status = 'failed', retry_count = retry_count + 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?;
                """,
                (video_id,),
            )
            return cur.rowcount > 0

    def update_metadata(self, video_id: int, file_name: str | None = None) -> bool:
        """Updates video metadata such as custom title or file name."""
        with db_session(self.db_path) as conn:
            if file_name:
                cur = conn.execute(
                    "UPDATE video_registry SET file_name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?;",
                    (file_name, video_id),
                )
                return cur.rowcount > 0
            return False

    def list_available(self) -> list[dict[str, Any]]:
        with db_session(self.db_path, write=False) as conn:
            rows = conn.execute("SELECT * FROM video_registry WHERE status = 'available' ORDER BY id ASC;").fetchall()
            return [dict(r) for r in rows]
