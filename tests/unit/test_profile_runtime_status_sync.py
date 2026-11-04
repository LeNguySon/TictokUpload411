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
        if hasattr(win, "profile_status_timer"):
            win.profile_status_timer.stop()
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
        win.thread_pool.pool.waitForDone(2000)
        app_instance.processEvents()

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
            win.thread_pool.pool.waitForDone(2000)
            app_instance.processEvents()

        # Reconciled status:
        assert prof_repo.get_by_id(p1)["status"] == "running"
        assert prof_repo.get_by_id(p2)["status"] == "stopped"

        win.scheduler_timer.stop()
        if hasattr(win, "profile_status_timer"):
            win.profile_status_timer.stop()
        win.profile_table.clearSelection()
        win.close()
        win.deleteLater()
        app_instance.processEvents()


def test_profile_table_widget_column_width_and_no_truncation(app_instance):
    """Verifies that Status Column 12 has StatusBadgeDelegate, adequate width (>= 125px), and UserRole data."""
    from src.presentation.delegates.status_badge_delegate import StatusBadgeDelegate

    table = ProfileTableWidget()
    # Check column width >= 125px and StatusBadgeDelegate attached
    assert table.columnWidth(12) >= 125
    assert isinstance(table.itemDelegateForColumn(12), StatusBadgeDelegate)

    # Check status rendering & tooltip
    profiles = [
        {"id": 1, "name": "Prof1", "status": "running"},
        {"id": 2, "name": "Prof2", "status": "stopped"},
        {"id": 3, "name": "Prof3", "status": "LIVE"},
    ]
    table.load_profiles(profiles)

    item_running = table.item(0, 12)
    assert item_running.data(Qt.ItemDataRole.UserRole) == "running"
    assert "running" in item_running.toolTip()

    item_stopped = table.item(1, 12)
    assert item_stopped.data(Qt.ItemDataRole.UserRole) == "stopped"
    assert "stopped" in item_stopped.toolTip()

    item_live = table.item(2, 12)
    assert item_live.data(Qt.ItemDataRole.UserRole) == "LIVE"


def test_orbita_launcher_sdk_session_running_and_port_probe():
    """Verifies that SDK sessions are tracked and validated via socket probe."""
    launcher = OrbitaLauncher(executable_path=Path("C:/dummy/chrome.exe"))
    prof_uuid = "test-uuid-12345"

    with patch("src.infrastructure.browser.orbita_launcher.is_port_open") as mock_port:
        mock_port.return_value = True
        launcher._active_sdk_sessions[prof_uuid] = "127.0.0.1:45678"

        # Check with uuid in dict
        assert launcher.is_profile_running({"id": 10, "uuid": prof_uuid}) is True

        # When port is closed (browser killed manually)
        mock_port.return_value = False
        assert launcher.is_profile_running({"id": 10, "uuid": prof_uuid}) is False
        # Stale session cleaned up
        assert prof_uuid not in launcher._active_sdk_sessions


def test_orbita_launcher_daemon_status_and_psutil_fallback():
    """Verifies fallback to SamMonny daemon API and psutil scan."""
    launcher = OrbitaLauncher(executable_path=Path("C:/dummy/chrome.exe"))
    prof_uuid = "daemon-uuid-67890"

    # 1. Daemon API says running
    with patch("sammonny.core.client.SamMonnyDaemonClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_prof = MagicMock()
        mock_prof.status = "running"
        mock_prof.port = None
        mock_client.get_profile.return_value = mock_prof
        mock_client_cls.return_value = mock_client

        assert launcher.is_profile_running({"id": 11, "uuid": prof_uuid}) is True

    # 2. psutil scan fallback
    with patch.object(launcher, "_scan_psutil_for_profile", return_value=True):
        assert launcher.is_profile_running({"id": 12, "uuid": "other-uuid"}) is True


def test_main_window_periodic_status_watcher_sync(isolated_db, app_instance):
    """Verifies that periodic status watcher detects process exit and updates cell directly."""
    db_file = isolated_db["db_file"]
    prof_repo = isolated_db["prof_repo"]
    p1 = isolated_db["p1"]
    prof_repo.update(p1, status="running")

    with patch("src.presentation.views.main_window.setTheme"):
        win = TikTokManagerMainWindow(db_path=db_file)
        win.thread_pool.pool.waitForDone(2000)
        app_instance.processEvents()

        # Profile is initially shown as running
        row = -1
        for r in range(win.profile_table.rowCount()):
            it = win.profile_table.item(r, 0)
            if it and it.data(Qt.ItemDataRole.UserRole).get("id") == p1:
                row = r
                break
        assert row >= 0

        # Now simulate browser closing: is_profile_running becomes False
        with patch.object(win.orbita_launcher, "is_profile_running", return_value=False):
            win._sync_active_profile_statuses()
            win.thread_pool.pool.waitForDone(2000)
            app_instance.processEvents()

        # Cell 12 must be updated to stopped
        item = win.profile_table.item(row, 12)
        assert item.text() == "stopped"
        assert prof_repo.get_by_id(p1)["status"] == "stopped"

        win.scheduler_timer.stop()
        if hasattr(win, "profile_status_timer"):
            win.profile_status_timer.stop()
        win.profile_table.clearSelection()
        win.close()
        win.deleteLater()
        app_instance.processEvents()
