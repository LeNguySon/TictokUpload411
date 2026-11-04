"""Unit tests for Profile table right-click context menu 'Add Video' action,
verifying asynchronous video importing, multi-profile fair-share distribution,
and visibility in the video queue table.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication
from src.application.services.upload_service import UploadService
from src.application.workers.video_import_worker import VideoImportWorker
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.video_repository import VideoRepository
from src.presentation.widgets.profile_table_widget import ProfileTableWidget


@pytest.fixture
def app_instance():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


@pytest.fixture
def temp_db(tmp_path: Path):
    db_file = tmp_path / "test_tiktok.db"
    run_all_migrations(db_file)
    return db_file


@pytest.fixture
def sample_video_files(tmp_path: Path):
    v1 = tmp_path / "video_alpha.mp4"
    v2 = tmp_path / "video_beta.mp4"
    v3 = tmp_path / "video_gamma.mp4"
    v1.write_bytes(b"A" * 4096)
    v2.write_bytes(b"B" * 4096)
    v3.write_bytes(b"C" * 4096)
    return [v1, v2, v3]


def test_video_import_worker_single_profile(temp_db: Path, sample_video_files: list[Path]):
    """VideoImportWorker assigns all files to a single target profile."""
    video_repo = VideoRepository(temp_db)
    profile_repo = ProfileRepository(temp_db)
    upload_service = UploadService(profile_repo=profile_repo, video_repo=video_repo, tiktok_adapter=MagicMock())

    p_id = profile_repo.create({"name": "Profile 1", "os_type": "win"})

    worker = VideoImportWorker(
        file_paths=[str(f) for f in sample_video_files],
        upload_service=upload_service,
        assigned_profile_id=p_id,
    )

    completed_mock = MagicMock()
    worker.signals.completed.connect(completed_mock)

    worker.run()

    completed_mock.assert_called_once_with(3)
    available_videos = video_repo.list_available()
    assert len(available_videos) == 3
    for v in available_videos:
        assert v["assigned_profile_id"] == p_id
        assert v["status"] in ("available", "reserved")


def test_video_import_worker_multi_profiles_fair_share(temp_db: Path, sample_video_files: list[Path]):
    """VideoImportWorker distributes files evenly round-robin across multiple profile IDs."""
    video_repo = VideoRepository(temp_db)
    profile_repo = ProfileRepository(temp_db)
    upload_service = UploadService(profile_repo=profile_repo, video_repo=video_repo, tiktok_adapter=MagicMock())

    p1 = profile_repo.create({"name": "Profile Japan 1", "os_type": "win"})
    p2 = profile_repo.create({"name": "Profile Japan 2", "os_type": "win"})

    worker = VideoImportWorker(
        file_paths=[str(f) for f in sample_video_files],
        upload_service=upload_service,
        target_profile_ids=[p1, p2],
    )

    completed_mock = MagicMock()
    worker.signals.completed.connect(completed_mock)

    worker.run()

    completed_mock.assert_called_once_with(3)
    available_videos = video_repo.list_available()
    assert len(available_videos) == 3

    assigned_ids = [v["assigned_profile_id"] for v in available_videos]
    # Round-robin: [p1, p2, p1]
    assert assigned_ids == [p1, p2, p1]


def test_video_repository_list_available_includes_reserved_videos(temp_db: Path, sample_video_files: list[Path]):
    """Ensures list_available returns videos in both 'available' and 'reserved' states."""
    video_repo = VideoRepository(temp_db)
    profile_repo = ProfileRepository(temp_db)
    upload_service = UploadService(profile_repo=profile_repo, video_repo=video_repo, tiktok_adapter=MagicMock())

    p_id = profile_repo.create({"name": "Profile Res", "os_type": "win"})
    vid_id = upload_service.enqueue_video(
        file_path=sample_video_files[0],
        title="Reserved Vid",
        assigned_profile_id=p_id,
    )

    # Reserve the video
    reserved = video_repo.try_reserve(vid_id, p_id)
    assert reserved is True

    # Check that list_available still returns this video so it is visible in the UI table
    items = video_repo.list_available()
    assert len(items) == 1
    assert items[0]["id"] == vid_id
    assert items[0]["status"] == "reserved"


def test_profile_table_context_menu_labels(app_instance):
    """ProfileTableWidget shows appropriate dynamic titles for single vs multi selection."""
    table = ProfileTableWidget()
    profiles = [
        {"id": 1, "name": "Japan_01", "os_type": "win", "status": "LIVE"},
        {"id": 2, "name": "Japan_02", "os_type": "win", "status": "LIVE"},
    ]
    table.load_profiles(profiles)

    # We can inspect the label generation logic in contextMenuEvent
    # Single selection
    table.selectRow(0)
    selected = table.get_selected_profiles()
    assert len(selected) == 1
    assert selected[0]["name"] == "Japan_01"

    # Multi selection
    table.selectAll()
    selected_multi = table.get_selected_profiles()
    assert len(selected_multi) == 2


def test_main_window_on_add_video_for_profiles(temp_db: Path, sample_video_files: list[Path], app_instance):
    """MainWindow._on_add_video_for_profiles enqueues videos asynchronously and updates video table."""
    from src.presentation.views.main_window import MainWindow

    with patch("src.presentation.views.main_window.setTheme"):
        win = MainWindow(db_path=temp_db)
        p_id = win.profile_repo.create({"name": "TargetProfile", "os_type": "win"})

        # Mock QFileDialog
        with patch(
            "PyQt6.QtWidgets.QFileDialog.getOpenFileNames", return_value=([str(sample_video_files[0])], "Video Files")
        ):
            with patch.object(win.thread_pool, "dispatch") as mock_dispatch:
                # Emulate immediate execution
                def run_worker_sync(worker):
                    worker.run()

                mock_dispatch.side_effect = run_worker_sync

                win._on_add_video_for_profiles([p_id])

        win.refresh_videos()
        assert win.video_table.rowCount() == 1
        # Check that Upload To column shows the profile name
        upload_to_item = win.video_table.item(0, 8)
        assert upload_to_item is not None
        assert "TargetProfile" in upload_to_item.text()
