"""
Unit tests for Multi-Project Folder Batch Video Distribution.
Verifies UploadService, FolderDistributionWorker, and BatchFolderUploadDialog
support distributing videos across multiple projects concurrently with strict project isolation.
Strict TDD - Phase RED -> GREEN -> REFACTOR.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication
from src.application.services.upload_service import UploadService
from src.application.workers.folder_distribution_worker import FolderDistributionWorker
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.video_repository import VideoRepository
from src.presentation.dialogs.batch_folder_upload_dialog import BatchFolderUploadDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    db_file = tmp_path / "multi_project_batch_test.db"
    run_all_migrations(db_file)
    return db_file


def test_upload_service_distribute_multi_project_batches(test_db: Path, tmp_path: Path):
    """Verifies distribute_multi_project_batches correctly isolates video pools to their respective project profiles."""
    proj_repo = ProjectRepository(test_db)
    prof_repo = ProfileRepository(test_db)
    video_repo = VideoRepository(test_db)
    adapter = MagicMock()
    upload_service = UploadService(profile_repo=prof_repo, video_repo=video_repo, tiktok_adapter=adapter)

    # 1. Setup Project 1 (Japan) and Project 2 (Korea)
    folder_jp = tmp_path / "videos_jp"
    folder_jp.mkdir()
    (folder_jp / "jp1.mp4").write_bytes(b"DATA_JP1" + b"\x00" * 1000)
    (folder_jp / "jp2.mp4").write_bytes(b"DATA_JP2" + b"\x00" * 1000)

    folder_kr = tmp_path / "videos_kr"
    folder_kr.mkdir()
    (folder_kr / "kr1.mp4").write_bytes(b"DATA_KR1" + b"\x00" * 1000)
    (folder_kr / "kr2.mp4").write_bytes(b"DATA_KR2" + b"\x00" * 1000)
    (folder_kr / "kr3.mp4").write_bytes(b"DATA_KR3" + b"\x00" * 1000)

    p_jp = proj_repo.create(name="Nhóm Japan", video_folder=str(folder_jp))
    p_kr = proj_repo.create(name="Nhóm Korea", video_folder=str(folder_kr))

    prof_jp1 = prof_repo.create({"uuid": "u-jp1", "name": "JP Acc 1", "project_id": p_jp, "storage_dir": "/jp1"})
    prof_jp2 = prof_repo.create({"uuid": "u-jp2", "name": "JP Acc 2", "project_id": p_jp, "storage_dir": "/jp2"})

    prof_kr1 = prof_repo.create({"uuid": "u-kr1", "name": "KR Acc 1", "project_id": p_kr, "storage_dir": "/kr1"})

    # 2. Prepare batches
    batches = [
        {
            "project_id": p_jp,
            "project_name": "Nhóm Japan",
            "folder_path": str(folder_jp),
            "profile_ids": [prof_jp1, prof_jp2],
        },
        {
            "project_id": p_kr,
            "project_name": "Nhóm Korea",
            "folder_path": str(folder_kr),
            "profile_ids": [prof_kr1],
        },
    ]

    progress_history = []

    def on_progress(cur: int, tot: int, msg: str):
        progress_history.append((cur, tot, msg))

    results = upload_service.distribute_multi_project_batches(
        project_batches=batches,
        min_interval_hours=2.0,
        deduplicate=True,
        progress_callback=on_progress,
    )

    # 3. Assertions
    # Total 2 JP + 3 KR = 5 videos distributed
    assert len(results) == 5
    assert len(progress_history) == 5

    # Check isolation: JP videos only assigned to JP accounts
    jp_distributed = [r for r in results if "jp" in r["file_name"].lower()]
    assert len(jp_distributed) == 2
    for r in jp_distributed:
        assert r["assigned_profile_id"] in [prof_jp1, prof_jp2]

    # Check isolation: KR videos only assigned to KR account
    kr_distributed = [r for r in results if "kr" in r["file_name"].lower()]
    assert len(kr_distributed) == 3
    for r in kr_distributed:
        assert r["assigned_profile_id"] == prof_kr1


def test_folder_distribution_worker_with_multi_project_batches(qapp, test_db: Path, tmp_path: Path):
    """Verifies FolderDistributionWorker accepts multiple project batches and emits unified progress."""
    proj_repo = ProjectRepository(test_db)
    prof_repo = ProfileRepository(test_db)
    video_repo = VideoRepository(test_db)
    adapter = MagicMock()
    upload_service = UploadService(profile_repo=prof_repo, video_repo=video_repo, tiktok_adapter=adapter)

    f1 = tmp_path / "f1"
    f1.mkdir()
    (f1 / "v1.mp4").write_bytes(b"V1_CONTENT" + b"\x00" * 1000)

    f2 = tmp_path / "f2"
    f2.mkdir()
    (f2 / "v2.mp4").write_bytes(b"V2_CONTENT" + b"\x00" * 1000)

    p1 = proj_repo.create(name="Project A")
    p2 = proj_repo.create(name="Project B")
    acc1 = prof_repo.create({"uuid": "ua", "name": "Acc A", "project_id": p1, "storage_dir": "/a"})
    acc2 = prof_repo.create({"uuid": "ub", "name": "Acc B", "project_id": p2, "storage_dir": "/b"})

    batches = [
        {"project_id": p1, "project_name": "Project A", "folder_path": str(f1), "profile_ids": [acc1]},
        {"project_id": p2, "project_name": "Project B", "folder_path": str(f2), "profile_ids": [acc2]},
    ]

    completed_payload = []
    progress_payload = []

    worker = FolderDistributionWorker(
        upload_service=upload_service,
        project_batches=batches,
    )
    worker.signals.progress.connect(lambda cur, tot, name: progress_payload.append((cur, tot, name)))
    worker.signals.completed.connect(lambda items: completed_payload.append(items))

    worker.run()

    assert len(completed_payload) == 1
    assert len(completed_payload[0]) == 2
    assert len(progress_payload) == 2


def test_batch_folder_upload_dialog_multi_project_table_ui(qapp, test_db: Path, tmp_path: Path):
    """Verifies BatchFolderUploadDialog renders multiple project rows with folder inputs and live counters."""
    proj_repo = ProjectRepository(test_db)
    prof_repo = ProfileRepository(test_db)
    video_repo = VideoRepository(test_db)
    adapter = MagicMock()
    upload_service = UploadService(profile_repo=prof_repo, video_repo=video_repo, tiktok_adapter=adapter)

    dir_jp = tmp_path / "vid_jp"
    dir_jp.mkdir()
    (dir_jp / "c1.mp4").write_bytes(b"CLIP1" + b"\x00" * 1000)
    (dir_jp / "c2.mp4").write_bytes(b"CLIP2" + b"\x00" * 1000)

    p1 = proj_repo.create(name="Chiến dịch Japan", video_folder=str(dir_jp))
    p2 = proj_repo.create(name="Chiến dịch US", video_folder="")

    prof_repo.create({"uuid": "p-jp-1", "name": "Acc JP 1", "project_id": p1, "storage_dir": "/jp1"})
    prof_repo.create({"uuid": "p-us-1", "name": "Acc US 1", "project_id": p2, "storage_dir": "/us1"})

    dlg = BatchFolderUploadDialog(
        profile_repo=prof_repo,
        upload_service=upload_service,
        project_repo=proj_repo,
    )

    # Project table should have rows for projects
    assert hasattr(dlg, "project_table")
    assert dlg.project_table.rowCount() >= 2

    # Check selected batches extraction
    selected_batches = dlg.get_selected_project_batches()
    # By default, rows with configured folders/accounts can be checked
    assert isinstance(selected_batches, list)
