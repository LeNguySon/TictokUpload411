"""
Unit tests for Project-Specific Video Source Binding, Recursive Batch Distribution,
and 1:1 Project Synchronization between Profile and Video Tables.
Strict TDD - Phase RED -> GREEN -> REFACTOR.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication, QDialog
from src.application.services.upload_service import UploadService
from src.application.workers.task_worker import drain_ui_tasks
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.video_repository import VideoRepository
from src.presentation.dialogs.batch_folder_upload_dialog import BatchFolderUploadDialog
from src.presentation.views.main_window import TikTokManagerMainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    db_file = tmp_path / "test_project_video_sync.db"
    run_all_migrations(db_file)
    return db_file


def test_batch_folder_upload_dialog_initial_folder_and_project_filtering(qapp, test_db: Path):
    """Verifies dialog auto-fills project folder and filters target profiles to active project."""
    proj_repo = ProjectRepository(test_db)
    prof_repo = ProfileRepository(test_db)
    u_svc = MagicMock()

    p1_id = proj_repo.create(name="Project Japan", video_folder="D:/videos/Japan")
    p2_id = proj_repo.create(name="Project Korea", video_folder="D:/videos/Korea")

    prof1_id = prof_repo.create({"uuid": "u-jp-01", "name": "Japan Acc 1", "project_id": p1_id, "storage_dir": "/p1"})
    prof_repo.create({"uuid": "u-kr-02", "name": "Korea Acc 2", "project_id": p2_id, "storage_dir": "/p2"})

    # Launch dialog bound to Project Japan
    dlg = BatchFolderUploadDialog(
        profile_repo=prof_repo,
        upload_service=u_svc,
        initial_folder="D:/videos/Japan",
        project_id=p1_id,
    )

    assert dlg.txt_folder.text() == "D:/videos/Japan"
    assert dlg.profile_table.rowCount() == 1
    # Only Japan account should be in the table
    id_item = dlg.profile_table.item(0, 1)
    assert id_item is not None
    assert int(id_item.text()) == prof1_id


def test_batch_folder_upload_dialog_recursive_scan_and_distribution(qapp, test_db: Path, tmp_path: Path):
    """Verifies batch dialog recursively discovers videos across subdirectories and distributes them."""
    proj_repo = ProjectRepository(test_db)
    prof_repo = ProfileRepository(test_db)
    video_repo = VideoRepository(test_db)
    adapter = MagicMock()
    u_svc = UploadService(profile_repo=prof_repo, video_repo=video_repo, tiktok_adapter=adapter)

    p_id = proj_repo.create(name="Japan Campaign")
    _ = prof_repo.create({"uuid": "u-rec-01", "name": "Japan Recurse", "project_id": p_id, "storage_dir": "/p"})

    # Create nested video structure
    v_root = tmp_path / "Japan_Root"
    v_sub = v_root / "Level1" / "Level2"
    v_sub.mkdir(parents=True)

    (v_root / "video_root.mp4").write_bytes(b"root content" + b"\x00" * 2000)
    (v_sub / "video_deep.mov").write_bytes(b"deep content" + b"\x00" * 2000)

    dlg = BatchFolderUploadDialog(
        profile_repo=prof_repo,
        upload_service=u_svc,
        initial_folder=str(v_root),
        project_id=p_id,
    )

    # Execute distribution
    success = dlg._execute_distribution()
    assert success is True
    assert len(dlg.distributed_videos) == 2

    # Check that both root and deep videos are registered
    file_paths = [item["file_path"] for item in dlg.distributed_videos]
    assert any("video_root" in fp for fp in file_paths)
    assert any("video_deep" in fp for fp in file_paths)


def test_video_repository_list_available_filtered_by_project(test_db: Path):
    """Verifies list_available filters videos by project_id and handles unassigned videos."""
    proj_repo = ProjectRepository(test_db)
    prof_repo = ProfileRepository(test_db)
    video_repo = VideoRepository(test_db)

    p1 = proj_repo.create(name="Market JP")
    p2 = proj_repo.create(name="Market KR")

    prof1 = prof_repo.create({"uuid": "u-jp", "name": "JP Acc", "project_id": p1, "storage_dir": "/jp"})
    prof2 = prof_repo.create({"uuid": "u-kr", "name": "KR Acc", "project_id": p2, "storage_dir": "/kr"})

    # Video 1 assigned to Japan
    v1 = video_repo.register_or_update("h1", "C:/v1.mp4", "V1_JP", 100, 1.0, assigned_profile_id=prof1)
    # Video 2 assigned to Korea
    v2 = video_repo.register_or_update("h2", "C:/v2.mp4", "V2_KR", 100, 1.0, assigned_profile_id=prof2)
    # Video 3 unassigned (available to all)
    v3 = video_repo.register_or_update("h3", "C:/v3.mp4", "V3_Unassigned", 100, 1.0, assigned_profile_id=None)

    # Filter for Japan (Project 1): Should contain V1 and V3, but NOT V2
    jp_videos = video_repo.list_available(project_id=p1)
    jp_ids = [v["id"] for v in jp_videos]
    assert v1 in jp_ids
    assert v3 in jp_ids
    assert v2 not in jp_ids

    # Filter for Korea (Project 2): Should contain V2 and V3, but NOT V1
    kr_videos = video_repo.list_available(project_id=p2)
    kr_ids = [v["id"] for v in kr_videos]
    assert v2 in kr_ids
    assert v3 in kr_ids
    assert v1 not in kr_ids

    # All projects (project_id=None): Should contain all 3
    all_videos = video_repo.list_available(project_id=None)
    all_ids = [v["id"] for v in all_videos]
    assert v1 in all_ids
    assert v2 in all_ids
    assert v3 in all_ids


def test_main_window_project_change_syncs_profiles_and_videos_and_batch_button(
    qapp, test_db: Path, monkeypatch, tmp_path: Path
):
    """Verifies MainWindow synchronizes profiles and videos on project selection and buttons match UI spec."""
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)

    proj_repo = ProjectRepository(test_db)
    prof_repo = ProfileRepository(test_db)
    video_repo = VideoRepository(test_db)

    folder_jp = tmp_path / "Videos_JP"
    folder_jp.mkdir()
    p1 = proj_repo.create(name="Dự án Japan", video_folder=str(folder_jp))
    p2 = proj_repo.create(name="Dự án Korea")

    prof1 = prof_repo.create({"uuid": "u1", "name": "Prof Japan", "project_id": p1, "storage_dir": "/jp"})
    prof2 = prof_repo.create({"uuid": "u2", "name": "Prof Korea", "project_id": p2, "storage_dir": "/kr"})

    video_repo.register_or_update("hash_jp", "C:/v_jp.mp4", "Video JP", 100, 1.0, assigned_profile_id=prof1)
    video_repo.register_or_update("hash_kr", "C:/v_kr.mp4", "Video KR", 100, 1.0, assigned_profile_id=prof2)

    window = TikTokManagerMainWindow(db_path=test_db)
    try:
        # Check toolbar button text exact match
        assert window.btn_batch_upload.text() == "Nạp Thư Mục Phân Bổ"

        # Initially 'Tất cả dự án' is selected
        assert window.project_combo.currentIndex() == 0
        assert window.profile_table.rowCount() == 2
        assert window.video_table.rowCount() == 2

        # Switch to 'Dự án Japan'
        jp_index = -1
        for idx in range(window.project_combo.count()):
            if window.project_combo.itemData(idx) == p1:
                jp_index = idx
                break
        assert jp_index > 0
        window.project_combo.setCurrentIndex(jp_index)
        drain_ui_tasks()  # loads/actions run on the UI pool since UI responsiveness P1

        # Profiles and videos should both be filtered to Japan project
        assert window.profile_table.rowCount() == 1
        assert window.video_table.rowCount() == 1

        # Verify initial video pick folder is resolved to Japan's folder
        assert window._get_initial_video_pick_folder() == str(folder_jp)

        # Trigger batch folder upload dialog
        window._on_open_batch_folder_upload()
    finally:
        window.close()
