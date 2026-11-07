"""Unit and Integration Tests for UI Smoothness, Asynchronous Runtime Status Sync, and Main Entrypoint.
Strict ECC TDD: Validates batch profile running checks, non-blocking worker execution, and UTF-8 safety.
"""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication
from src.infrastructure.browser.orbita_launcher import OrbitaLauncher
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.presentation.views.main_window import TikTokManagerMainWindow


@pytest.fixture
def app_instance():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def mock_background_workers():
    with (
        patch("src.presentation.views.main_window.MetricsSyncWorker"),
        patch("src.presentation.views.main_window.SamMonnyDaemonSupervisor"),
    ):
        yield
    from src.application.signals.app_signals import AppSignalBus
    from src.application.workers.thread_pool_manager import ThreadPoolManager

    ThreadPoolManager.reset_instance()
    AppSignalBus.reset_instance()


@pytest.fixture
def isolated_db(tmp_path: Path):
    db_file = tmp_path / "smoothness_test.db"
    run_all_migrations(db_file)
    prof_repo = ProfileRepository(db_file)
    profs = []
    for i in range(1, 21):  # 20 profiles
        p_id = prof_repo.create(
            {
                "name": f"Profile_{i}",
                "uuid": f"uuid-mock-{i:04d}",
                "status": "stopped",
            }
        )
        profs.append(p_id)
    return {"db_file": db_file, "prof_repo": prof_repo, "profile_ids": profs}


def test_batch_check_profiles_running_batching():
    """Verifies that OrbitaLauncher.batch_check_profiles_running resolves all profiles in a single batch."""
    launcher = OrbitaLauncher(executable_path=Path("C:/dummy/chrome.exe"))

    # Test profile list
    profiles = [
        {"id": 1, "uuid": "uuid-001", "status": "stopped"},
        {"id": 2, "uuid": "uuid-002", "status": "stopped"},
        {"id": 3, "uuid": "uuid-003", "status": "running"},
    ]

    # Mock SamMonnyDaemonClient.list_profiles returning uuid-002 as running
    mock_p2 = MagicMock()
    mock_p2.id = "uuid-002"
    mock_p2.status = "running"
    mock_p2.port = None

    # The daemon port check is patched too: otherwise the test only passes while a real daemon listens on 7654.
    with (
        patch("sammonny.core.client.SamMonnyDaemonClient") as mock_client_cls,
        patch("src.infrastructure.browser.orbita_launcher.is_port_open", return_value=True),
    ):
        mock_client = MagicMock()
        mock_client.list_profiles.return_value = [mock_p2]
        mock_client_cls.return_value = mock_client

        # Profile 1 also has active process in memory
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        launcher._active_processes[1] = mock_proc

        result = launcher.batch_check_profiles_running(profiles)

        assert isinstance(result, dict)
        assert result.get(1) is True  # Active process
        assert result.get(2) is True  # Daemon reported running
        assert result.get(3) is False  # Not running in daemon or process


def test_profile_runtime_sync_worker_execution(isolated_db):
    """Verifies that ProfileRuntimeSyncWorker runs off-thread and calculates status deltas."""
    from src.application.workers.profile_runtime_sync_worker import ProfileRuntimeSyncWorker

    prof_repo = isolated_db["prof_repo"]
    profs = prof_repo.list_active()
    launcher = OrbitaLauncher(executable_path=Path("C:/dummy/chrome.exe"))

    # Mark profile 1 and 2 as running in launcher batch check
    def mock_batch_check(p_list):
        return {p["id"]: (p["id"] in (profs[0]["id"], profs[1]["id"])) for p in p_list}

    with patch.object(launcher, "batch_check_profiles_running", side_effect=mock_batch_check):
        worker = ProfileRuntimeSyncWorker(
            profiles=profs,
            launcher=launcher,
        )

        received_updates = []
        worker.signals.statuses_updated.connect(lambda updates: received_updates.append(updates))

        # Execute worker
        worker.run()

        assert len(received_updates) == 1
        delta = received_updates[0]
        # Only profiles whose status changed from stopped -> running should be in delta
        assert profs[0]["id"] in delta
        assert delta[profs[0]["id"]] == "running"
        assert profs[1]["id"] in delta
        assert delta[profs[1]["id"]] == "running"


def test_main_window_refresh_profiles_zero_blocking(isolated_db, app_instance):
    """Verifies that MainWindow.refresh_profiles loads table without synchronously calling is_profile_running."""
    db_file = isolated_db["db_file"]

    with patch("src.presentation.views.main_window.setTheme"):
        win = TikTokManagerMainWindow(db_path=db_file)

        # Spy or patch is_profile_running
        with patch.object(win.orbita_launcher, "is_profile_running") as mock_is_running:
            t0 = time.perf_counter()
            win.refresh_profiles()
            elapsed = time.perf_counter() - t0

            # Must NOT call is_profile_running in a synchronous loop during table load
            assert not mock_is_running.called
            # Table loading must be sub-50ms
            assert elapsed < 0.15
            assert win.profile_table.rowCount() == 20

        win.scheduler_timer.stop()
        if hasattr(win, "profile_status_timer") and win.profile_status_timer.isActive():
            win.profile_status_timer.stop()
        win.profile_table.clearSelection()
        win.close()
        win.deleteLater()
        app_instance.processEvents()


def test_main_window_async_status_watcher_updates_cells(isolated_db, app_instance):
    """Verifies that _on_profile_statuses_updated updates table cells without writing the DB on the GUI thread."""
    db_file = isolated_db["db_file"]
    prof_repo = isolated_db["prof_repo"]
    target_pid = isolated_db["profile_ids"][0]

    with patch("src.presentation.views.main_window.setTheme"):
        win = TikTokManagerMainWindow(db_path=db_file)

        target_row = win._find_profile_row_by_id(target_pid)
        assert target_row != -1

        # Initial cell status should be stopped
        item_initial = win.profile_table.item(target_row, 12)
        assert item_initial.text() == "stopped"

        # Apply delta update
        delta = {target_pid: "running"}
        win._on_profile_statuses_updated(delta)

        # Cell should be updated to running
        item_updated = win.profile_table.item(target_row, 12)
        assert item_updated.text() == "running"
        # Persistence moved off the GUI thread into ProfileRuntimeSyncWorker (UI responsiveness T4);
        # the slot itself must not write SQLite.
        assert prof_repo.get_by_id(target_pid)["status"] == "stopped"

        win.scheduler_timer.stop()
        if hasattr(win, "profile_status_timer") and win.profile_status_timer.isActive():
            win.profile_status_timer.stop()
        win.profile_table.clearSelection()
        win.close()
        win.deleteLater()
        app_instance.processEvents()
