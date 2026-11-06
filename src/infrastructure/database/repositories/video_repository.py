"""
Video Repository: Manages local video assets, SHA-256 deduplication, and atomic reservation.
Clean Architecture: Infrastructure Layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.infrastructure.database.connection import DEFAULT_DB_PATH, db_session
from src.infrastructure.logging.redaction_logger import RedactionFilter


class VideoRepository:
    """Repository for managing the `video_registry` table."""

    # Upper bound for stored upload error reasons (SDK errors can embed whole HTTP bodies).
    MAX_ERROR_MESSAGE_CHARS = 1000

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH

    def register_or_update(
        self,
        video_hash: str,
        file_path: str,
        file_name: str,
        file_size: int,
        mtime: float,
        assigned_profile_id: int | None = None,
        schedule_time: str | None = None,
    ) -> int:
        """Registers a new video file or updates metadata if already tracked."""
        with db_session(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO video_registry (
                    video_hash, file_path, file_name, file_size, mtime, assigned_profile_id, schedule_time, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'available')
                ON CONFLICT(video_hash) DO UPDATE SET
                    file_path = excluded.file_path,
                    file_name = excluded.file_name,
                    file_size = excluded.file_size,
                    mtime = excluded.mtime,
                    assigned_profile_id = COALESCE(excluded.assigned_profile_id, video_registry.assigned_profile_id),
                    schedule_time = COALESCE(excluded.schedule_time, video_registry.schedule_time),
                    updated_at = CURRENT_TIMESTAMP;
                """,
                (video_hash, file_path, file_name, file_size, mtime, assigned_profile_id, schedule_time),
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

    def claim_for_upload(self, video_id: int, profile_id: int) -> bool:
        """Atomically moves a video to 'uploading' for ``profile_id``.

        Claimable: 'available', 'failed' (explicit retry), or 'reserved' for this same profile (the
        auto-dispatch scheduler reserves before handing the video to a worker). A video already
        'uploading' or 'published', or reserved for another profile, is never taken.
        """
        with db_session(self.db_path) as conn:
            cur = conn.execute(
                """
                UPDATE video_registry
                SET status = 'uploading', assigned_profile_id = ?, error_message = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                  AND (status IN ('available', 'failed') OR (status = 'reserved' AND assigned_profile_id = ?));
                """,
                (profile_id, video_id, profile_id),
            )
            return cur.rowcount > 0

    def defer_to_app_schedule(self, video_id: int, profile_id: int, schedule_time: str) -> bool:
        """Claimed video back to 'available' with its schedule and profile: the app's scheduler posts it."""
        with db_session(self.db_path) as conn:
            cur = conn.execute(
                """
                UPDATE video_registry
                SET status = 'available', schedule_time = ?, assigned_profile_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status IN ('uploading', 'reserved');
                """,
                (schedule_time, profile_id, video_id),
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
                    error_message = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?;
                """,
                (published_profile_id, tiktok_video_id, video_id),
            )
            return cur.rowcount > 0

    def mark_error(self, video_id: int, error_message: str | None = None) -> bool:
        """Marks video as failed, increments retry count and stores the (redacted, truncated) reason."""
        reason = None
        if error_message:
            reason = RedactionFilter.redact(str(error_message)).strip()[: self.MAX_ERROR_MESSAGE_CHARS] or None
        with db_session(self.db_path) as conn:
            cur = conn.execute(
                """
                UPDATE video_registry
                SET status = 'failed', retry_count = retry_count + 1, error_message = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?;
                """,
                (reason, video_id),
            )
            return cur.rowcount > 0

    def update_metadata(
        self,
        video_id: int,
        file_name: str | None = None,
        file_path: str | None = None,
        schedule_time: str | None = None,
        assigned_profile_id: int | None = None,
    ) -> bool:
        """Updates video metadata such as custom title, file name, schedule time, or assigned profile."""
        updates: list[str] = []
        params: list[Any] = []
        if file_name is not None:
            updates.append("file_name = ?")
            params.append(file_name)
        if file_path is not None:
            updates.append("file_path = ?")
            params.append(file_path)
        if schedule_time is not None:
            updates.append("schedule_time = ?")
            params.append(schedule_time)
        if assigned_profile_id is not None:
            updates.append("assigned_profile_id = ?")
            params.append(assigned_profile_id)

        if not updates:
            return False

        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(video_id)
        sql = f"UPDATE video_registry SET {', '.join(updates)} WHERE id = ?;"

        with db_session(self.db_path) as conn:
            cur = conn.execute(sql, tuple(params))
            return cur.rowcount > 0

    def update_schedule(
        self,
        video_id: int,
        schedule_time: str | None,
        assigned_profile_id: int | None = None,
    ) -> bool:
        """Sets or clears the automated schedule time and optionally assigns target profile."""
        with db_session(self.db_path) as conn:
            if assigned_profile_id is not None:
                cur = conn.execute(
                    """
                    UPDATE video_registry
                    SET schedule_time = ?, assigned_profile_id = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?;
                    """,
                    (schedule_time, assigned_profile_id, video_id),
                )
            else:
                cur = conn.execute(
                    """
                    UPDATE video_registry
                    SET schedule_time = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?;
                    """,
                    (schedule_time, video_id),
                )
            return cur.rowcount > 0

    def batch_update_schedules(self, items: list[dict[str, Any]]) -> int:
        """Atomically updates schedule time and assigned profiles for multiple videos."""
        if not items:
            return 0
        updated = 0
        with db_session(self.db_path) as conn:
            for item in items:
                vid = item.get("id")
                sched = item.get("schedule_time")
                prof_id = item.get("assigned_profile_id")
                if vid is None:
                    continue
                if prof_id is not None:
                    cur = conn.execute(
                        """
                        UPDATE video_registry
                        SET schedule_time = ?, assigned_profile_id = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?;
                        """,
                        (sched, prof_id, vid),
                    )
                else:
                    cur = conn.execute(
                        """
                        UPDATE video_registry
                        SET schedule_time = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?;
                        """,
                        (sched, vid),
                    )
                updated += cur.rowcount
        return updated

    def list_scheduled_due(self, max_time_iso: str | None = None) -> list[dict[str, Any]]:
        """Returns all available videos whose schedule_time <= max_time_iso."""
        from datetime import datetime

        cutoff = max_time_iso or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with db_session(self.db_path, write=False) as conn:
            rows = conn.execute(
                """
                SELECT v.*, p.name AS assigned_profile_name
                FROM video_registry v
                LEFT JOIN profiles p ON v.assigned_profile_id = p.id
                WHERE v.status = 'available'
                  AND v.schedule_time IS NOT NULL
                  AND v.schedule_time != ''
                  AND v.schedule_time <= ?
                ORDER BY v.schedule_time ASC, v.id ASC;
                """,
                (cutoff,),
            ).fetchall()
            return [dict(r) for r in rows]

    def delete(self, video_id: int) -> bool:
        """Deletes a single video record by ID."""
        with db_session(self.db_path) as conn:
            cur = conn.execute("DELETE FROM video_registry WHERE id = ?;", (video_id,))
            return cur.rowcount > 0

    def delete_many(self, video_ids: list[int]) -> int:
        """Deletes multiple video records by their IDs."""
        if not video_ids:
            return 0
        placeholders = ", ".join("?" for _ in video_ids)
        with db_session(self.db_path) as conn:
            cur = conn.execute(f"DELETE FROM video_registry WHERE id IN ({placeholders});", tuple(video_ids))
            return cur.rowcount

    def list_available(
        self,
        project_id: int | None = None,
        only_available: bool = True,
    ) -> list[dict[str, Any]]:
        # The queue table (only_available=False) also shows failed videos so they can be retried.
        status_clause = (
            "v.status = 'available'"
            if only_available
            else "v.status IN ('available', 'reserved', 'uploading', 'failed')"
        )
        with db_session(self.db_path, write=False) as conn:
            if project_id is not None:
                query = f"""
                SELECT v.*, p.name AS assigned_profile_name, pr.name AS project_name
                FROM video_registry v
                LEFT JOIN profiles p ON v.assigned_profile_id = p.id
                LEFT JOIN projects pr ON p.project_id = pr.id
                WHERE {status_clause}
                  AND (v.assigned_profile_id IS NULL OR p.project_id = ?)
                ORDER BY v.id ASC;
                """
                rows = conn.execute(query, (project_id,)).fetchall()
            else:
                query = f"""
                SELECT v.*, p.name AS assigned_profile_name, pr.name AS project_name
                FROM video_registry v
                LEFT JOIN profiles p ON v.assigned_profile_id = p.id
                LEFT JOIN projects pr ON p.project_id = pr.id
                WHERE {status_clause}
                ORDER BY v.id ASC;
                """
                rows = conn.execute(query).fetchall()
            return [dict(r) for r in rows]
