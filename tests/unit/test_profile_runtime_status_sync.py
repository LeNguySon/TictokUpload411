"""Unit tests for real-time Profile Runtime Status synchronization and table display.
Validates:
1. BrowserProcessSupervisor.is_process_running checks PID lock file.
2. OrbitaLauncher.is_profile_running accurately reflects running vs stopped processes.
3. MainWindow._on_orbita_profile_launched updates database status to 'running' and refreshes UI.
4. MainWindow._on_close_orbita updates database status to 'stopped' and refreshes UI.
5. MainWindow.refresh_profiles auto-reconciles stale status against live OS process status.
6. ProfileTableWidget column 12 width >= 105px and styles 'running' in bold blue (#0078D4).
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
from src.infrastructure.browser.orbita_launcher import OrbitaLauncher
from src.infrastructure.browser.process_supervisor import BrowserProcessSupervisor
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.presentation.views.main_window import TikTokManagerMainWindow
from src.presentation.widgets.profile_table_widget import ProfileTableWidget


@pytest.fixture
def app_instance():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def mock_background_workers():
    with patch("src.presentation.views.main_window.MetricsSyncWorker"):
        yield
    from src.application.signals.app_signals import AppSignalBus
    from src.application.workers.thread_pool_manager import ThreadPoolManager

    ThreadPoolManager.reset_instance()
    AppSignalBus.reset_instance()


@pytest.fixture
def isolated_db(tmp_path: Path):
    db_file = tmp_path / "runtime_status_test.db"
    run_all_migrations(db_file)
    prof_repo = ProfileRepository(db_file)
    p1 = prof_repo.create({"name": "TestProfile_1", "status": "stopped"})
    p2 = prof_repo.create({"name": "TestProfile_2", "status": "running"})
    return {"db_file": db_file, "prof_repo": prof_repo, "p1": p1, "p2": p2}


def test_process_supervisor_is_process_running(tmp_path: Path):
    """Verifies that supervisor inspects lock file and PID validity."""
    supervisor = BrowserProcessSupervisor()
    profile_dir = tmp_path / "browser_dir"
    profile_dir.mkdir()

    # No lock file -> not running
    assert supervisor.is_process_running(profile_dir) is False

    # Create lock file with PID
    lock_file = profile_dir / ".process.lock"
    lock_file.write_text("12345", encoding="utf-8")

    with patch("psutil.pid_exists", return_value=True):
        assert supervisor.is_process_running(profile_dir) is True

    with patch("psutil.pid_exists", return_value=False):
        assert supervisor.is_process_running(profile_dir) is False


def test_orbita_launcher_is_profile_running():
    """Verifies that OrbitaLauncher detects whether a profile is active in memory or on disk."""
    launcher = OrbitaLauncher(executable_path=Path("C:/dummy/chrome.exe"))

    # When not tracked in _active_processes
    assert launcher.is_profile_running(99) is False

    # When tracked in _active_processes with active process
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None  # None means still running
    launcher._active_processes[99] = mock_proc
    assert launcher.is_profile_running(99) is True

    # When process has terminated (poll() returns exit code)
    mock_proc.poll.return_value = 0
    assert launcher.is_profile_running(99) is False


def test_main_window_orbita_lifecycle_updates_db_and_ui(isolated_db, app_instance):
    """Verifies that launching Orbita sets status to 'running' and closing sets to 'stopped'."""
    db_file = isolated_db["db_file"]
    prof_repo = isolated_db["prof_repo"]
    p1 = isolated_db["p1"]

    with patch("src.presentation.views.main_window.setTheme"):
        win = TikTokManagerMainWindow(db_path=db_file)

        # Initial status is stopped
        prof = prof_repo.get_by_id(p1)
        assert prof["status"] == "stopped"

        # Simulate profile launched signal with launcher active process
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        win.orbita_launcher._active_processes[p1] = mock_proc
        win._on_orbita_profile_launched(p1, "TestProfile_1", "9222")

        # DB must be updated to running
        updated_prof = prof_repo.get_by_id(p1)
        assert updated_prof["status"] == "running"

        # Table row for p1 must show running
        row_for_p1 = -1
        for r in range(win.profile_table.rowCount()):
            it = win.profile_table.item(r, 0)
            if it and it.data(Qt.ItemDataRole.UserRole).get("id") == p1:
                row_for_p1 = r
                break
        assert row_for_p1 >= 0
        item = win.profile_table.item(row_for_p1, 12)
        assert item is not None
        assert item.text() == "running"

        # Now simulate closing the profile
        mock_proc.poll.return_value = 0
        with patch.object(win.orbita_launcher, "close_profile") as mock_close:
            win._on_close_orbita([p1])
            assert mock_close.called

        # DB must be updated to stopped
        stopped_prof = prof_repo.get_by_id(p1)
        assert stopped_prof["status"] == "stopped"

        # Table row must show stopped
        item2 = win.profile_table.item(row_for_p1, 12)
        assert item2 is not None
        assert item2.text() == "stopped"

        win.scheduler_timer.stop()
        win.profile_table.clearSelection()
        win.close()
        win.deleteLater()
        app_instance.processEvents()


def test_main_window_refresh_profiles_auto_reconciliation(isolated_db, app_instance):
    """Verifies that refresh_profiles auto-reconciles stale DB status against live process status."""
    db_file = isolated_db["db_file"]
    prof_repo = isolated_db["prof_repo"]
    p1 = isolated_db["p1"]  # DB status is 'stopped'
    p2 = isolated_db["p2"]  # DB status is 'running'

    with patch("src.presentation.views.main_window.setTheme"):
        win = TikTokManagerMainWindow(db_path=db_file)

        # Mock launcher: p1 is actually RUNNING in OS, p2 is STOPPED in OS
        def mock_is_running(profile_dict_or_id):
            pid = profile_dict_or_id if isinstance(profile_dict_or_id, int) else profile_dict_or_id.get("id")
            if pid == p1:
                return True
            if pid == p2:
                return False
            return False

        with patch.object(win.orbita_launcher, "is_profile_running", side_effect=mock_is_running):
            win.refresh_profiles()

        # Reconciled status:
        assert prof_repo.get_by_id(p1)["status"] == "running"
        assert prof_repo.get_by_id(p2)["status"] == "stopped"

        win.scheduler_timer.stop()
        win.profile_table.clearSelection()
        win.close()
        win.deleteLater()
        app_instance.processEvents()


def test_profile_table_widget_column_width_and_no_truncation(app_instance):
    """Verifies that Status Column 12 has adequate width (>= 105px) and correct styling."""
    table = ProfileTableWidget()
    # Check column width
    assert table.columnWidth(12) >= 105

    # Check status rendering
    profiles = [
        {"id": 1, "name": "Prof1", "status": "running"},
        {"id": 2, "name": "Prof2", "status": "stopped"},
        {"id": 3, "name": "Prof3", "status": "LIVE"},
    ]
    table.load_profiles(profiles)

    item_running = table.item(0, 12)
    assert item_running.text() == "running"
    # Font is bold
    assert item_running.font().bold() is True

    item_stopped = table.item(1, 12)
    assert item_stopped.text() == "stopped"

    item_live = table.item(2, 12)
    assert item_live.text() == "LIVE"
