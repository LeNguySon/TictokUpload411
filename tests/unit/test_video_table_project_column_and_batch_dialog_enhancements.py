"""
Unit tests for VideoQueueTableWidget Project Column and BatchFolderUploadDialog UI Enhancements.
Strict TDD - Phase RED -> GREEN -> REFACTOR.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication
from src.application.services.upload_service import UploadService
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.video_repository import VideoRepository
from src.presentation.dialogs.batch_folder_upload_dialog import BatchFolderUploadDialog
from src.presentation.widgets.table_helpers import get_video_table_headers
from src.presentation.widgets.video_queue_table_widget import VideoQueueTableWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    db_file = tmp_path / "test_ui_enhancements.db"
    run_all_migrations(db_file)
    return db_file


def test_video_table_headers_include_project_column():
    """Verifies get_video_table_headers contains 'Dự Án' at column index 2."""
    headers = get_video_table_headers()
    assert len(headers) == 15
    assert headers[0] == "STT"
    assert headers[1] == "Tiêu đề"
    assert headers[2] == "Dự Án"
    assert "Upload To" in headers


def test_video_repository_list_available_returns_project_name(test_db: Path):
    """Verifies list_available joins project_name from projects table."""
    proj_repo = ProjectRepository(test_db)
    prof_repo = ProfileRepository(test_db)
    video_repo = VideoRepository(test_db)

    p_id = proj_repo.create(name="Nhóm Japan Thị Trường")
    prof_id = prof_repo.create({"uuid": "u-jp-99", "name": "JP Creator", "project_id": p_id, "storage_dir": "/jp"})

    video_repo.register_or_update(
        video_hash="h_jp_test",
        file_path="D:/videos/Japan/video1.mp4",
        file_name="Video Nhật Bản 01",
        file_size=1024,
        mtime=1.0,
        assigned_profile_id=prof_id,
    )

    available = video_repo.list_available(project_id=p_id)
    assert len(available) == 1
    assert available[0]["project_name"] == "Nhóm Japan Thị Trường"
    assert available[0]["assigned_profile_name"] == "JP Creator"


def test_video_queue_table_renders_project_column(qapp, test_db: Path):
    """Verifies VideoQueueTableWidget populates column 2 with the project name or source directory."""
    table = VideoQueueTableWidget()
    assert table.columnCount() == 15
    assert table.horizontalHeaderItem(2).text() == "Dự Án"

    videos = [
        {
            "id": 1,
            "file_name": "Video Tokyo Drift",
            "project_name": "Nhóm Japan",
            "file_path": "D:/videos/Japan/clip1.mp4",
            "assigned_profile_name": "JP Acc 1",
            "status": "available",
        },
        {
            "id": 2,
            "file_name": "Video Seoul Vlog",
            "project_name": None,
            "file_path": "D:/videos/Korea/clip2.mp4",
            "assigned_profile_name": None,
            "status": "available",
        },
    ]

    table.load_videos(videos)
    assert table.rowCount() == 2

    # Row 0: Assigned to project "Nhóm Japan"
    item_row0 = table.item(0, 2)
    assert item_row0 is not None
    assert item_row0.text() == "Nhóm Japan"

    # Row 1: Unassigned, falls back to parent folder name "Korea"
    item_row1 = table.item(1, 2)
    assert item_row1 is not None
    assert item_row1.text() == "Korea"


def test_batch_folder_upload_dialog_project_banner_and_file_scan_counter(qapp, test_db: Path, tmp_path: Path):
    """Verifies BatchFolderUploadDialog displays project name and live scanned file count."""
    proj_repo = ProjectRepository(test_db)
    prof_repo = ProfileRepository(test_db)
    adapter = MagicMock()
    video_repo = VideoRepository(test_db)
    u_svc = UploadService(profile_repo=prof_repo, video_repo=video_repo, tiktok_adapter=adapter)

    p_id = proj_repo.create(name="Chiến Dịch Hàn Quốc (Korea)", video_folder=str(tmp_path))
    prof_repo.create({"uuid": "u-kr-1", "name": "Korea 01", "project_id": p_id, "storage_dir": "/k1"})

    # Create dummy videos in nested structure
    sub_folder = tmp_path / "Sub1" / "Sub2"
    sub_folder.mkdir(parents=True)
    (tmp_path / "vid1.mp4").write_bytes(b"sample video bytes" + b"\x00" * 2000)
    (sub_folder / "vid2.mov").write_bytes(b"sample video bytes 2" + b"\x00" * 2000)

    dlg = BatchFolderUploadDialog(
        profile_repo=prof_repo,
        upload_service=u_svc,
        initial_folder=str(tmp_path),
        project_id=p_id,
        project_name="Chiến Dịch Hàn Quốc (Korea)",
    )

    # Check project banner / title
    assert hasattr(dlg, "lbl_project_badge")
    assert "Chiến Dịch Hàn Quốc" in dlg.lbl_project_badge.text()

    # Check live recursive file counter
    assert hasattr(dlg, "lbl_scan_info")
    assert "2 video" in dlg.lbl_scan_info.text()
