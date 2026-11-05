"""video_registry.error_message: the reason of the last failed upload survives a table reload.

Before, mark_error() accepted an error_message but there was no column, so the reason was lost and
the queue table (which already renders `error_message`) showed nothing after a refresh.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.video_repository import VideoRepository


@pytest.fixture
def repos(tmp_path: Path):
    db = tmp_path / "err.db"
    run_all_migrations(db)
    pid = ProfileRepository(db).create({"name": "P", "uuid": "uuid-err-0001"})
    videos = VideoRepository(db)
    vid = videos.register_or_update(
        video_hash="h1", file_path=str(tmp_path / "a.mp4"), file_name="a", file_size=1, mtime=1.0
    )
    return db, videos, vid, pid


def test_existing_database_gets_error_message_column(tmp_path: Path):
    db = tmp_path / "old.db"
    run_all_migrations(db)
    with sqlite3.connect(db) as conn:  # simulate a database created before the column existed
        conn.execute("ALTER TABLE video_registry DROP COLUMN error_message")
        assert "error_message" not in {r[1] for r in conn.execute("PRAGMA table_info(video_registry)")}
    run_all_migrations(db)
    with sqlite3.connect(db) as conn:
        assert "error_message" in {r[1] for r in conn.execute("PRAGMA table_info(video_registry)")}


def test_mark_error_persists_reason(repos):
    _, videos, vid, _ = repos
    videos.mark_error(vid, error_message="Upload timeout at chunk 3/5")
    row = videos.get_by_id(vid)
    assert row["status"] == "failed"
    assert row["error_message"] == "Upload timeout at chunk 3/5"
    assert vid in [v["id"] for v in videos.list_available(only_available=False) if v.get("error_message")]


def test_error_message_never_stores_secrets(repos):
    _, videos, vid, _ = repos
    videos.mark_error(
        vid, error_message="HTTP 403 with sessionid=abcdef123456 and Bearer eyJhbGciOiJIUzI1NiJ9.payloadpayload"
    )
    stored = videos.get_by_id(vid)["error_message"]
    assert "abcdef123456" not in stored and "eyJhbGci" not in stored
    assert "HTTP 403" in stored


def test_error_message_is_truncated(repos):
    _, videos, vid, _ = repos
    videos.mark_error(vid, error_message="x" * 10_000)
    assert len(videos.get_by_id(vid)["error_message"]) <= VideoRepository.MAX_ERROR_MESSAGE_CHARS


def test_retry_clears_previous_error_and_publish_keeps_it_clear(repos):
    _, videos, vid, pid = repos
    videos.mark_error(vid, error_message="first attempt failed")
    assert videos.claim_for_upload(video_id=vid, profile_id=pid)
    assert videos.get_by_id(vid)["error_message"] is None
    videos.mark_error(vid, error_message="second attempt failed")
    videos.mark_published(video_id=vid, published_profile_id=pid, tiktok_video_id="7")
    assert videos.get_by_id(vid)["error_message"] is None


def test_queue_table_shows_persisted_error(qtbot, repos):
    from src.presentation.widgets.video_queue_table_widget import VideoQueueTableWidget

    _, videos, vid, _ = repos
    videos.mark_error(vid, error_message="Proxy chết")
    table = VideoQueueTableWidget()
    qtbot.addWidget(table)
    table.load_videos(videos.list_available(only_available=False))
    assert "Proxy chết" in table.item(table.find_row_by_video_id(vid), 11).text()
