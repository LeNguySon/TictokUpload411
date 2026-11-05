"""
Unit and Integration tests for Video Scheduling & Auto-Dispatch Pipeline.
Strict TDD - Phase RED -> GREEN -> REFACTOR.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication
from src.infrastructure.database.connection import db_session
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.video_repository import VideoRepository
from src.presentation.widgets.video_queue_table_widget import VideoQueueTableWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    db_file = tmp_path / "test_scheduling.db"
    run_all_migrations(db_file)
    prof_repo = ProfileRepository(db_file)
    prof_repo.create({"uuid": "prof-u1", "name": "Profile 1", "storage_dir": "/p1", "user_agent": "Mozilla/5.0"})
    prof_repo.create({"uuid": "prof-u2", "name": "Profile 2", "storage_dir": "/p2", "user_agent": "Mozilla/5.0"})
    return db_file


def test_schema_migration_includes_schedule_time_column(test_db: Path):
    """Verifies video_registry table includes schedule_time column after migrations."""
    with db_session(test_db, write=False) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(video_registry);").fetchall()]
    assert "schedule_time" in cols


def test_video_repository_update_schedule_persists(test_db: Path):
    """Verifies update_schedule persists schedule_time and assigned_profile_id to SQLite."""
    repo = VideoRepository(test_db)
    vid_id = repo.register_or_update(
        video_hash="hash_sched_01",
        file_path="C:/videos/video1.mp4",
        file_name="Video 1 Title",
        file_size=10240,
        mtime=123456.0,
    )

    sched_time = "2026-11-04 17:30:00"
    success = repo.update_schedule(vid_id, schedule_time=sched_time, assigned_profile_id=1)
    assert success is True

    # Open with a fresh repo instance to ensure persistence on disk
    fresh_repo = VideoRepository(test_db)
    row = fresh_repo.get_by_id(vid_id)
    assert row is not None
    assert row["schedule_time"] == sched_time
    assert row["assigned_profile_id"] == 1


def test_video_repository_list_scheduled_due(test_db: Path):
    """Verifies list_scheduled_due accurately filters due videos."""
    repo = VideoRepository(test_db)

    # 1. Past due video (available)
    v1 = repo.register_or_update(
        video_hash="hash_past_01",
        file_path="C:/videos/past1.mp4",
        file_name="Past Video 1",
        file_size=10240,
        mtime=123456.0,
    )
    repo.update_schedule(v1, schedule_time="2026-11-04 10:00:00")

    # 2. Due right now (available)
    v2 = repo.register_or_update(
        video_hash="hash_now_02",
        file_path="C:/videos/now2.mp4",
        file_name="Now Video 2",
        file_size=10240,
        mtime=123456.0,
    )
    repo.update_schedule(v2, schedule_time="2026-11-04 12:00:00")

    # 3. Future video (available)
    v3 = repo.register_or_update(
        video_hash="hash_future_03",
        file_path="C:/videos/future3.mp4",
        file_name="Future Video 3",
        file_size=10240,
        mtime=123456.0,
    )
    repo.update_schedule(v3, schedule_time="2026-11-04 19:00:00")

    # 4. Past video but already published
    v4 = repo.register_or_update(
        video_hash="hash_published_04",
        file_path="C:/videos/pub4.mp4",
        file_name="Published Video 4",
        file_size=10240,
        mtime=123456.0,
    )
    repo.update_schedule(v4, schedule_time="2026-11-04 09:00:00")
    repo.mark_published(v4, published_profile_id=1, tiktok_video_id="tiktok_999")

    # Query for due items up to 12:30:00
    due = repo.list_scheduled_due(max_time_iso="2026-11-04 12:30:00")
    due_ids = [item["id"] for item in due]

    assert v1 in due_ids
    assert v2 in due_ids
    assert v3 not in due_ids  # Future
    assert v4 not in due_ids  # Already published


def test_batch_update_schedules(test_db: Path):
    """Verifies atomic batch scheduling of multiple videos."""
    repo = VideoRepository(test_db)
    v1 = repo.register_or_update("h1", "C:/v1.mp4", "V1", 100, 1.0)
    v2 = repo.register_or_update("h2", "C:/v2.mp4", "V2", 200, 2.0)

    items = [
        {"id": v1, "schedule_time": "2026-11-04 15:00:00", "assigned_profile_id": 1},
        {"id": v2, "schedule_time": "2026-11-04 15:30:00", "assigned_profile_id": 2},
    ]
    updated_count = repo.batch_update_schedules(items)
    assert updated_count == 2

    row1 = repo.get_by_id(v1)
    row2 = repo.get_by_id(v2)
    assert row1["schedule_time"] == "2026-11-04 15:00:00"
    assert row1["assigned_profile_id"] == 1
    assert row2["schedule_time"] == "2026-11-04 15:30:00"
    assert row2["assigned_profile_id"] == 2


def test_video_queue_table_widget_renders_schedule_and_profile(qapp):
    """Verifies VideoQueueTableWidget shows schedule_time on Col 6 and assigned profile on Col 7."""
    table = VideoQueueTableWidget()
    sample_videos = [
        {
            "id": 101,
            "file_name": "Test Viral Dance",
            "schedule_time": "2026-11-04 16:45:00",
            "assigned_profile_name": "Profile VIP 1",
            "status": "available",
        }
    ]
    table.load_videos(sample_videos)

    # Col 1: Title
    assert table.item(0, 1).text() == "Test Viral Dance"
    # Col 7: Schedule time
    assert table.item(0, 7).text() == "2026-11-04 16:45:00"
    # Col 8: Upload To
    assert table.item(0, 8).text() == "Profile VIP 1"


def test_auto_dispatch_scheduler_dispatches_worker(test_db: Path):
    """Verifies scheduler logic identifies due video, reserves it and dispatches worker."""
    from src.presentation.views.main_window import TikTokManagerMainWindow

    repo = VideoRepository(test_db)
    vid_id = repo.register_or_update(
        video_hash="hash_due_test",
        file_path="C:/videos/due.mp4",
        file_name="Due Video",
        file_size=5000,
        mtime=1.0,
    )
    repo.update_schedule(vid_id, schedule_time="2026-11-04 10:00:00", assigned_profile_id=1)

    # Create dummy MainWindow instance with mocks
    main_win = MagicMock()
    main_win.video_repo = repo
    main_win.thread_pool = MagicMock()
    main_win.profile_table = MagicMock()
    main_win.profile_table.get_selected_profile_ids.return_value = [1]
    main_win.upload_service = MagicMock()
    main_win.signal_bus = MagicMock()

    # Call the auto-dispatch method logic
    TikTokManagerMainWindow._check_scheduled_queue(main_win)

    # Worker should have been dispatched on the dedicated upload pool (UI responsiveness T8)
    assert main_win.thread_pool.dispatch_upload.called
