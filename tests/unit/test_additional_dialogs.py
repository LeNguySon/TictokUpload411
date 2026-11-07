"""
Unit tests for Additional Dialogs: TableSettings, ScheduleDialog, VideoMetadata, SyncTransfer, UserGuide, and OrbitaLauncher.
Strict TDD - Phase 2 (RED -> GREEN)
"""

from datetime import datetime
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication
from src.application.workers.task_worker import drain_ui_tasks
from src.infrastructure.browser.orbita_launcher import OrbitaLauncher
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
from src.presentation.dialogs.api_cookie_dialog import ApiCookieDialog
from src.presentation.dialogs.permissions_dialog import PermissionsDialog
from src.presentation.dialogs.schedule_dialog import generate_staggered_schedule
from src.presentation.dialogs.sync_transfer_dialog import (
    export_project_dataset,
    import_project_dataset,
)
from src.presentation.dialogs.table_settings_dialog import TableSettingsDialog
from src.presentation.dialogs.user_guide_dialog import UserGuideDialog
from src.presentation.dialogs.video_metadata_dialog import VideoMetadataDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_generate_staggered_schedule():
    start_time = datetime(2026, 11, 4, 14, 0, 0)
    schedules = generate_staggered_schedule(
        start_time=start_time,
        count=3,
        interval_minutes=30,
        random_jitter_minutes=5,
    )
    assert len(schedules) == 3
    t0 = datetime.fromisoformat(schedules[0])
    t1 = datetime.fromisoformat(schedules[1])
    t2 = datetime.fromisoformat(schedules[2])
    assert t0 >= start_time
    assert t1 > t0
    assert t2 > t1


def test_orbita_launcher_argument_building():
    launcher = OrbitaLauncher(executable_path="C:/Program Files/Orbita/chrome.exe")
    args = launcher.build_launch_args(
        user_data_dir="C:/profiles/p1",
        proxy_uri="http://user:pass@103.20.5.10:8080",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0.0.0",
        canvas_noise=8.0,
    )
    expected_dir = f"--user-data-dir={Path('C:/profiles/p1').resolve()}"
    assert expected_dir in args
    assert "--proxy-server=http://103.20.5.10:8080" in args
    assert "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0.0.0" in args
    assert any("canvas" in a.lower() or "fingerprint" in a.lower() for a in args)


def test_table_settings_dialog_instantiation(qapp):
    dlg = TableSettingsDialog(hidden_columns={1, 3})
    assert 1 in dlg.hidden_columns
    assert 3 in dlg.hidden_columns
    assert len(dlg._checkboxes) == len(dlg.headers)
    dlg.close()


def test_video_metadata_dialog(qapp):
    video = {
        "file_name": "dance_video.mp4",
        "title": "dance_video",
        "privacy_level": "PUBLIC_TO_EVERYONE",
    }
    dlg = VideoMetadataDialog(video)
    dlg.txt_title.setText("Updated Title")
    dlg._on_save()
    assert drain_ui_tasks(timeout_s=15)  # new profiles are created off the GUI thread
    assert dlg.video_data["title"] == "Updated Title"
    dlg.close()


def test_sync_transfer_dataset_export_and_import(tmp_path):
    db_file = tmp_path / "test_sync.db"
    run_all_migrations(db_file)
    project_repo = ProjectRepository(db_file)
    profile_repo = ProfileRepository(db_file)
    proxy_repo = ProxyRepository(db_file)

    p_id = project_repo.create(name="Project Sync")
    px_id = proxy_repo.create(host="1.1.1.1", port=8080)
    profile_repo.create(name="Profile Sync", project_id=p_id, proxy_id=px_id, tiktok_id="@syncuser")

    zip_file = tmp_path / "export_test.zip"
    exported_count = export_project_dataset(
        zip_path=zip_file,
        project_id=p_id,
        profile_repo=profile_repo,
        proxy_repo=proxy_repo,
        project_repo=project_repo,
    )
    assert exported_count == 1
    assert zip_file.exists()

    # Import into fresh database
    db_file_new = tmp_path / "test_import.db"
    run_all_migrations(db_file_new)
    project_repo_new = ProjectRepository(db_file_new)
    profile_repo_new = ProfileRepository(db_file_new)
    proxy_repo_new = ProxyRepository(db_file_new)

    imported_profiles, imported_proxies = import_project_dataset(
        zip_path=zip_file,
        profile_repo=profile_repo_new,
        proxy_repo=proxy_repo_new,
        project_repo=project_repo_new,
    )
    assert imported_profiles == 1
    assert imported_proxies == 1

    active = profile_repo_new.list_active()
    assert len(active) == 1
    assert active[0]["name"] == "Profile Sync"


def test_user_guide_dialog_tabs(qapp):
    dlg = UserGuideDialog()
    assert dlg.tabs.count() == 5
    dlg.close()


def test_api_cookie_dialog_instantiation(qapp):
    dlg = ApiCookieDialog()
    assert dlg.txt_client_key is not None
    dlg.close()


def test_permissions_dialog_url_generation(qapp):
    dlg = PermissionsDialog()
    dlg.txt_client_key.setText("test_app_key_123")
    dlg._on_generate_url()
    assert "test_app_key_123" in dlg.txt_auth_url.text()
    assert "https://www.tiktok.com/v2/auth/authorize/" in dlg.txt_auth_url.text()
    dlg.close()
