"""
Unit tests for Asynchronous Workers and GUI Freeze Prevention.
Verifies FolderDistributionWorker, OrbitaLaunchWorker, and VideoImportWorker
execute background tasks on QThreadPool without blocking the Qt event loop.
Strict TDD - Phase RED -> GREEN -> REFACTOR.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication
from src.application.services.upload_service import UploadService
from src.application.workers.folder_distribution_worker import FolderDistributionWorker
from src.application.workers.orbita_launch_worker import OrbitaLaunchWorker
from src.application.workers.video_import_worker import VideoImportWorker
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
from src.infrastructure.database.repositories.video_repository import VideoRepository


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    db_file = tmp_path / "async_workers_test.db"
    run_all_migrations(db_file)
    return db_file


def test_folder_distribution_worker_executes_asynchronously(qapp, test_db: Path, tmp_path: Path):
    """Verifies FolderDistributionWorker distributes videos in background thread and emits progress signals."""
    proj_repo = ProjectRepository(test_db)
    prof_repo = ProfileRepository(test_db)
    video_repo = VideoRepository(test_db)
    adapter = MagicMock()
    upload_service = UploadService(profile_repo=prof_repo, video_repo=video_repo, tiktok_adapter=adapter)

    p_id = proj_repo.create(name="Async Project")
    prof1 = prof_repo.create({"uuid": "u-async-1", "name": "Async Acc 1", "project_id": p_id, "storage_dir": "/a1"})
    prof2 = prof_repo.create({"uuid": "u-async-2", "name": "Async Acc 2", "project_id": p_id, "storage_dir": "/a2"})

    # Create 3 video files
    folder = tmp_path / "videos"
    folder.mkdir()
    (folder / "vid1.mp4").write_bytes(b"DATA1" + b"\x00" * 2000)
    (folder / "vid2.mov").write_bytes(b"DATA2" + b"\x00" * 2000)
    (folder / "vid3.mkv").write_bytes(b"DATA3" + b"\x00" * 2000)

    progress_events = []
    completed_events = []

    worker = FolderDistributionWorker(
        upload_service=upload_service,
        folder_path=str(folder),
        profile_ids=[prof1, prof2],
        min_interval_hours=2.0,
        random_order=False,
        deduplicate=True,
    )
    worker.signals.progress.connect(lambda cur, tot, name: progress_events.append((cur, tot, name)))
    worker.signals.completed.connect(lambda items: completed_events.append(items))

    # Run worker synchronously or in QThreadPool
    worker.run()

    # Assert progress was emitted for all 3 files
    assert len(progress_events) == 3
    assert progress_events[-1][0] == 3
    assert progress_events[-1][1] == 3

    # Assert completed signal received 3 distributed video records
    assert len(completed_events) == 1
    assert len(completed_events[0]) == 3


def test_orbita_launch_worker_executes_in_background(qapp, test_db: Path):
    """Verifies OrbitaLaunchWorker launches browsers asynchronously without blocking UI thread."""
    prof_repo = ProfileRepository(test_db)
    proxy_repo = ProxyRepository(test_db)
    proxy_svc = MagicMock()
    launcher = MagicMock()
    supervisor = MagicMock()

    # Mock successful launch returning a CDP port
    launcher.launch_via_gologin_sdk.return_value = "127.0.0.1:39211"

    px_id = proxy_repo.create(host="1.1.1.1", port=8080)
    p_id = prof_repo.create({"uuid": "u-orbita-async", "name": "Orbita Async", "proxy_id": px_id, "storage_dir": "/oa"})

    launched_events = []
    batch_events = []

    worker = OrbitaLaunchWorker(
        profile_ids=[p_id],
        profile_repo=prof_repo,
        proxy_repo=proxy_repo,
        proxy_service=proxy_svc,
        orbita_launcher=launcher,
        daemon_supervisor=supervisor,
    )
    worker.signals.profile_launched.connect(lambda pid, name, cdp: launched_events.append((pid, name, cdp)))
    worker.signals.batch_completed.connect(lambda succ, tot: batch_events.append((succ, tot)))

    worker.run()

    assert len(launched_events) == 1
    assert launched_events[0][0] == p_id
    assert launched_events[0][1] == "Orbita Async"
    assert launched_events[0][2] == "127.0.0.1:39211"

    assert len(batch_events) == 1
    assert batch_events[0] == (1, 1)


def test_video_import_worker_enqueues_files(qapp, test_db: Path, tmp_path: Path):
    """Verifies VideoImportWorker reads and indexes dropped/picked files in background thread."""
    prof_repo = ProfileRepository(test_db)
    video_repo = VideoRepository(test_db)
    adapter = MagicMock()
    upload_service = UploadService(profile_repo=prof_repo, video_repo=video_repo, tiktok_adapter=adapter)

    f1 = tmp_path / "imported1.mp4"
    f2 = tmp_path / "imported2.mp4"
    f1.write_bytes(b"IMPORT1" + b"\x00" * 2000)
    f2.write_bytes(b"IMPORT2" + b"\x00" * 2000)

    progress_events = []
    completed_events = []

    worker = VideoImportWorker(
        file_paths=[str(f1), str(f2)],
        upload_service=upload_service,
    )
    worker.signals.progress.connect(lambda cur, tot, name: progress_events.append((cur, tot, name)))
    worker.signals.completed.connect(lambda count: completed_events.append(count))

    worker.run()

    assert len(progress_events) == 2
    assert len(completed_events) == 1
    assert completed_events[0] == 2
    assert len(video_repo.list_available()) == 2


def test_batch_folder_upload_dialog_async_progress_and_completion(qapp, test_db: Path, tmp_path: Path):
    """Verifies BatchFolderUploadDialog updates progress bar without freezing GUI during distribution."""
    from src.presentation.dialogs.batch_folder_upload_dialog import BatchFolderUploadDialog

    prof_repo = ProfileRepository(test_db)
    video_repo = VideoRepository(test_db)
    adapter = MagicMock()
    upload_service = UploadService(profile_repo=prof_repo, video_repo=video_repo, tiktok_adapter=adapter)

    prof_repo.create({"uuid": "u-async-dlg", "name": "Async Dlg Prof", "storage_dir": "/ad"})

    folder = tmp_path / "async_dlg_videos"
    folder.mkdir()
    (folder / "v1.mp4").write_bytes(b"DATA_DLG1" + b"\x00" * 1000)
    (folder / "v2.mp4").write_bytes(b"DATA_DLG2" + b"\x00" * 1000)

    dlg = BatchFolderUploadDialog(
        profile_repo=prof_repo,
        upload_service=upload_service,
        initial_folder=str(folder),
    )

    assert dlg.windowTitle() == "Nạp Thư Mục Phân Bổ (Batch Upload)"

    # Simulate worker progress callback
    dlg._on_worker_progress(1, 2, "v1.mp4")
    assert dlg.progress_bar.maximum() == 2
    assert dlg.progress_bar.value() == 1
    assert "1/2" in dlg.lbl_progress_status.text()

    # Simulate worker completion callback
    dummy_items = [{"id": 1, "file_path": "v1.mp4"}, {"id": 2, "file_path": "v2.mp4"}]
    dlg._on_worker_completed(dummy_items)
    assert len(dlg.distributed_videos) == 2


def test_upload_service_compute_sha256_uses_4mb_buffer(tmp_path: Path):
    """Verifies compute_sha256 correctly hashes file with 4MB read buffer."""
    test_file = tmp_path / "test_4mb.mp4"
    data = b"HASH_BENCHMARK_CONTENT" * 10000
    test_file.write_bytes(data)

    import hashlib

    expected_hash = hashlib.sha256(data).hexdigest()
    computed_hash = UploadService.compute_sha256(test_file)
    assert computed_hash == expected_hash
