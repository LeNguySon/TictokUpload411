"""
Unit and Integration tests for Project-Specific Video Folders and TikTok Studio Native Cloud Scheduling.
Strict TDD - Phase RED -> GREEN -> REFACTOR.
"""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication
from src.application.services.upload_service import UploadService
from src.infrastructure.database.connection import db_session
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.video_repository import VideoRepository
from src.presentation.dialogs.schedule_dialog import ScheduleVideoDialog, round_to_nearest_5_minutes

FUTURE_SCHEDULE = (datetime.now() + timedelta(hours=2)).strftime(
    "%Y-%m-%d %H:%M:%S"
)  # relative: TikTok only schedules 15 min .. 10 days ahead


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    db_file = tmp_path / "test_project_folders.db"
    run_all_migrations(db_file)
    return db_file


def test_projects_schema_includes_video_folder_column(test_db: Path):
    """Verifies projects table includes video_folder column after migrations."""
    with db_session(test_db, write=False) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(projects);").fetchall()]
    assert "video_folder" in cols


def test_project_repository_crud_with_video_folder(test_db: Path, tmp_path: Path):
    """Verifies ProjectRepository creates and updates video_folder."""
    repo = ProjectRepository(test_db)
    japan_folder = str(tmp_path / "videos_japan")
    korea_folder = str(tmp_path / "videos_korea")

    proj_id = repo.create(
        name="Nhóm Japan",
        description="Dự án thị trường Nhật Bản",
        color="#E81123",
        video_folder=japan_folder,
    )
    p = repo.get_by_id(proj_id)
    assert p is not None
    assert p["name"] == "Nhóm Japan"
    assert p["video_folder"] == japan_folder

    # Update to Korea folder
    updated = repo.update(proj_id, video_folder=korea_folder)
    assert updated is True

    p2 = repo.get_by_id(proj_id)
    assert p2["video_folder"] == korea_folder


def test_round_to_nearest_5_minutes_helper():
    """Verifies rounding to nearest 5 minutes for TikTok Studio constraints."""
    assert round_to_nearest_5_minutes(0) == 0
    assert round_to_nearest_5_minutes(2) == 0
    assert round_to_nearest_5_minutes(3) == 5
    assert round_to_nearest_5_minutes(7) == 5
    assert round_to_nearest_5_minutes(8) == 10
    assert round_to_nearest_5_minutes(34) == 35
    assert round_to_nearest_5_minutes(58) == 55
    assert round_to_nearest_5_minutes(59) == 55


def test_schedule_video_dialog_studio_schedule_toggle(qapp):
    """Verifies ScheduleVideoDialog has Studio schedule checkbox and valid constraints."""
    dlg = ScheduleVideoDialog(video_count=3)
    assert hasattr(dlg, "chk_studio_schedule")
    assert dlg.chk_studio_schedule.text() == "Lên lịch trực tiếp vào TikTok Studio (Cloud Schedule)"

    # Toggle on Studio schedule
    dlg.chk_studio_schedule.setChecked(True)
    dlg._on_apply()

    assert dlg.is_studio_schedule is True
    assert len(dlg.generated_schedules) == 3


def test_upload_service_propagates_schedule_time_to_adapter(test_db: Path, tmp_path: Path):
    """Verifies UploadService.execute_upload propagates schedule_time to the TikTok adapter."""
    prof_repo = ProfileRepository(test_db)
    prof_id = prof_repo.create({"uuid": "u-sched-test", "name": "Studio Tester", "storage_dir": "/p"})

    video_repo = VideoRepository(test_db)
    v_file = tmp_path / "test_clip.mp4"
    v_file.write_bytes(b"dummy mp4 video bytes")

    vid_id = video_repo.register_or_update(
        video_hash="hash_clip_01",
        file_path=str(v_file),
        file_name="Viral Clip Title",
        file_size=v_file.stat().st_size,
        mtime=v_file.stat().st_mtime,
        schedule_time=FUTURE_SCHEDULE,
    )

    mock_adapter = MagicMock()
    mock_adapter.upload_video.return_value = MagicMock(success=True, publish_id="tiktok_pub_888", error=None)

    svc = UploadService(profile_repo=prof_repo, video_repo=video_repo, tiktok_adapter=mock_adapter)
    res = svc.execute_upload(video_id=vid_id, profile_id=prof_id, schedule_time=FUTURE_SCHEDULE)

    assert res.success is True
    assert mock_adapter.upload_video.called
    kwargs = mock_adapter.upload_video.call_args.kwargs
    assert kwargs.get("schedule_time") == FUTURE_SCHEDULE


def test_get_initial_video_pick_folder_logic(test_db: Path, tmp_path: Path):
    """Verifies MainWindow resolves initial video folder from active project."""
    from src.presentation.views.main_window import TikTokManagerMainWindow

    japan_dir = tmp_path / "Japan_Videos"
    japan_dir.mkdir()

    proj_repo = ProjectRepository(test_db)
    p_id = proj_repo.create(name="Japan Market", video_folder=str(japan_dir))

    main_win = MagicMock()
    main_win.project_repo = proj_repo
    main_win.project_combo = MagicMock()
    main_win.project_combo.currentData.return_value = p_id

    resolved_folder = TikTokManagerMainWindow._get_initial_video_pick_folder(main_win)
    assert resolved_folder == str(japan_dir)
