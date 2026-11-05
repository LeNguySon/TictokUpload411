"""UI responsiveness Sprint P1 (T5-T7) — see docs/03_work_breakdown/ui_responsiveness_fix_plan.md.

T5: profile/video table reloads read SQLite on a background pool; stale results are discarded.
T6: the video table paints progress with a delegate instead of one ProgressBar widget per row.
T7: blocking actions (close Orbita, rotate proxy, clean browser, post-upload isolation,
    folder scans) run off the GUI thread.
"""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PyQt6.QtGui import QDropEvent
from PyQt6.QtWidgets import QApplication

MAIN = threading.main_thread()
WAIT_MS = 5000


def _recorder(result=None):
    """Callable that records the thread it ran on."""
    calls: list[threading.Thread] = []

    def fn(*args, **kwargs):
        calls.append(threading.current_thread())
        return result(*args, **kwargs) if callable(result) else result

    fn.calls = calls  # type: ignore[attr-defined]
    return fn


def _off_gui(calls: list[threading.Thread]) -> bool:
    return bool(calls) and all(t is not MAIN for t in calls)


# ---------------------------------------------------------------------------
# TaskWorker / UI pool
# ---------------------------------------------------------------------------
def test_task_worker_runs_off_gui_and_delivers_result_on_gui(qtbot):
    from src.application.workers.task_worker import run_task

    work = _recorder(result=lambda: 42)
    delivered: list[tuple[object, threading.Thread]] = []
    run_task(work, on_result=lambda r: delivered.append((r, threading.current_thread())))
    qtbot.waitUntil(lambda: bool(delivered), timeout=WAIT_MS)

    assert _off_gui(work.calls)
    assert delivered == [(42, MAIN)]


def test_task_worker_reports_errors_on_gui(qtbot):
    from src.application.workers.task_worker import run_task

    def boom():
        raise ValueError("disk on fire")

    errors: list[str] = []
    run_task(boom, on_error=errors.append)
    qtbot.waitUntil(lambda: bool(errors), timeout=WAIT_MS)
    assert "disk on fire" in errors[0]


def test_ui_pool_is_separate_from_upload_pool():
    from PyQt6.QtCore import QThreadPool
    from src.application.workers.task_worker import ui_thread_pool

    assert ui_thread_pool() is not QThreadPool.globalInstance()
    assert ui_thread_pool() is ui_thread_pool()


# ---------------------------------------------------------------------------
# Main window fixture
# ---------------------------------------------------------------------------
@pytest.fixture
def main_window(qtbot, tmp_path: Path):
    from src.infrastructure.database.migrations.runner import run_all_migrations
    from src.infrastructure.database.repositories.profile_repository import ProfileRepository

    db_file = tmp_path / "p1.db"
    run_all_migrations(db_file)
    repo = ProfileRepository(db_file)
    ids = [repo.create({"name": f"Profile_{i}", "uuid": f"uuid-p1-{i:04d}", "status": "stopped"}) for i in range(1, 6)]

    with (
        patch("src.presentation.views.main_window.MetricsSyncWorker"),
        patch("src.presentation.views.main_window.SamMonnyDaemonSupervisor"),
        patch("src.presentation.views.main_window.setTheme"),
        patch("src.presentation.views.main_window.InfoBar"),
    ):
        from src.presentation.views.main_window import TikTokManagerMainWindow

        win = TikTokManagerMainWindow(db_path=db_file)
        win.scheduler_timer.stop()
        win.profile_status_timer.stop()
        win._trigger_async_status_sync = MagicMock()
        yield win, ids, repo
        win.close()
        win.deleteLater()
        QApplication.processEvents()


# ---------------------------------------------------------------------------
# T5 — async table loads
# ---------------------------------------------------------------------------
def test_initial_load_is_populated_synchronously(main_window):
    win, ids, _ = main_window
    assert win.profile_table.rowCount() == len(ids)


def test_refresh_profiles_reads_db_off_gui_thread(main_window, qtbot):
    win, ids, repo = main_window
    new_id = repo.create({"name": "Fresh", "uuid": "uuid-p1-fresh", "status": "stopped"})
    spy = _recorder(result=repo.list_active)
    with patch.object(win.profile_repo, "list_active", side_effect=spy):
        win.refresh_profiles()
        qtbot.waitUntil(lambda: win.profile_table.row_for_profile_id(new_id) is not None, timeout=WAIT_MS)
    assert _off_gui(spy.calls)


def test_refresh_videos_reads_db_off_gui_thread(main_window, qtbot):
    win, _, _ = main_window
    rows = [{"id": 1, "file_name": "a.mp4", "status": "available"}, {"id": 2, "file_name": "b.mp4"}]
    spy = _recorder(result=rows)
    with patch.object(win.video_repo, "list_available", side_effect=spy):
        win.refresh_videos()
        qtbot.waitUntil(lambda: win.video_table.rowCount() == 2, timeout=WAIT_MS)
    assert _off_gui(spy.calls)
    assert "/ 2" in win.lbl_video_header.text()


def test_stale_profile_load_result_is_discarded(main_window):
    win, ids, _ = main_window
    stale_gen = win._profile_load_gen
    win._profile_load_gen += 1  # a newer refresh was requested meanwhile
    win._apply_profile_load(stale_gen, [{"id": 999, "name": "stale"}])
    assert win.profile_table.rowCount() == len(ids)
    assert win.profile_table.row_for_profile_id(999) is None


# ---------------------------------------------------------------------------
# T6 — progress delegate
# ---------------------------------------------------------------------------
def test_video_table_paints_progress_without_cell_widgets(qtbot):
    from src.presentation.delegates.progress_bar_delegate import ProgressBarDelegate
    from src.presentation.widgets.video_queue_table_widget import VideoQueueTableWidget

    table = VideoQueueTableWidget()
    qtbot.addWidget(table)
    table.load_videos([{"id": i, "file_name": f"v{i}.mp4", "download_progress": 30} for i in range(1, 51)])

    assert isinstance(table.itemDelegateForColumn(10), ProgressBarDelegate)
    assert all(table.cellWidget(r, 10) is None for r in range(table.rowCount()))
    assert table.progress_value(7) == 30


def test_update_progress_sets_delegate_value(qtbot):
    from src.presentation.widgets.video_queue_table_widget import VideoQueueTableWidget

    table = VideoQueueTableWidget()
    qtbot.addWidget(table)
    table.load_videos([{"id": 5, "file_name": "a.mp4"}])
    table.update_progress(5, 45.6)
    assert table.progress_value(5) == 45
    table.update_progress(5, 180.0)
    assert table.progress_value(5) == 100
    assert table.progress_value(12345) is None


# ---------------------------------------------------------------------------
# T7 — blocking actions run off the GUI thread
# ---------------------------------------------------------------------------
def test_close_orbita_runs_off_gui_thread(main_window, qtbot):
    win, ids, _ = main_window
    spy = _recorder(result=True)
    with patch.object(win.orbita_launcher, "close_profile", side_effect=spy):
        win._on_close_orbita([ids[0]])
        qtbot.waitUntil(lambda: bool(spy.calls), timeout=WAIT_MS)
        row = win.profile_table.row_for_profile_id(ids[0])
        qtbot.waitUntil(lambda: win.profile_table.item(row, 12).text() == "stopped", timeout=WAIT_MS)
    assert _off_gui(spy.calls)


def test_rotate_proxy_runs_off_gui_thread(main_window, qtbot):
    win, ids, _ = main_window
    spy = _recorder(result={"ok": True})
    with (
        patch.object(win.profile_repo, "get_by_id", return_value={"id": ids[0], "proxy_id": 7}),
        patch.object(win.proxy_repo, "get_by_id", return_value={"id": 7, "change_ip_url": "http://rotate"}),
        patch.object(win.proxy_service, "rotate_proxy_ip", side_effect=spy),
        patch.object(win, "refresh_profiles") as refresh,
    ):
        win._on_rotate_proxy_selected([ids[0]])
        qtbot.waitUntil(lambda: refresh.called, timeout=WAIT_MS)
    assert _off_gui(spy.calls)


def test_clean_browser_runs_off_gui_thread(main_window, qtbot):
    win, _, _ = main_window
    spy = _recorder(result={"formatted_freed": "1 MB"})
    with (
        patch("src.infrastructure.browser.cache_cleaner.BrowserCacheCleaner.clean_cache", side_effect=spy),
        patch(
            "src.infrastructure.browser.process_supervisor.BrowserProcessSupervisor.cleanup_orphan_browsers",
            return_value=[],
        ),
        patch(
            "src.infrastructure.browser.process_supervisor.BrowserProcessSupervisor.trim_working_set",
            return_value={"freed_mb": 0.0},
        ),
    ):
        win._on_clean_browser()
        qtbot.waitUntil(lambda: bool(spy.calls), timeout=WAIT_MS)
    assert _off_gui(spy.calls)


def test_upload_completed_auto_advance_runs_off_gui_thread(main_window, qtbot):
    """UploadService isolates the file itself; the GUI handler only reads the queue (off-GUI) to auto-advance."""
    win, _, _ = main_window
    win.switch_auto.setChecked(True)
    win.profile_table.selectRow(0)
    spy = _recorder(result=[])
    with (
        patch.object(win.video_repo, "list_available", side_effect=spy),
        patch.object(win.upload_service, "isolate_video_file") as isolate,
    ):
        win._on_upload_completed(1, "pub-1")
        qtbot.waitUntil(lambda: bool(spy.calls), timeout=WAIT_MS)
    assert _off_gui(spy.calls)
    isolate.assert_not_called()


def test_batch_dialog_folder_count_runs_off_gui_thread(qtbot, tmp_path: Path):
    from src.infrastructure.database.migrations.runner import run_all_migrations
    from src.infrastructure.database.repositories.profile_repository import ProfileRepository
    from src.infrastructure.database.repositories.project_repository import ProjectRepository
    from src.presentation.dialogs import batch_folder_upload_dialog as mod

    db_file = tmp_path / "dlg.db"
    run_all_migrations(db_file)
    project_id = ProjectRepository(db_file).create(name="Dự án P1")
    folder = tmp_path / "vids"
    folder.mkdir()
    for i in range(3):
        (folder / f"v{i}.mp4").write_bytes(b"x")

    real = mod.count_valid_videos_in_folder
    spy = _recorder(result=real)
    with patch.object(mod, "count_valid_videos_in_folder", side_effect=spy):
        dlg = mod.BatchFolderUploadDialog(
            profile_repo=ProfileRepository(db_file),
            upload_service=MagicMock(),
            initial_folder=str(folder),
            project_id=project_id,
            project_name="Dự án P1",
        )
        qtbot.addWidget(dlg)
        qtbot.waitUntil(lambda: "3 video" in dlg.lbl_scan_info.text(), timeout=WAIT_MS)
    assert _off_gui(spy.calls)


def test_dropping_a_folder_scans_off_gui_thread(qtbot, tmp_path: Path):
    from src.presentation.widgets import video_queue_table_widget as mod

    folder = tmp_path / "drop"
    (folder / "_posted").mkdir(parents=True)
    (folder / "a.mp4").write_bytes(b"x")
    (folder / "_posted" / "old.mp4").write_bytes(b"x")

    table = mod.VideoQueueTableWidget()
    qtbot.addWidget(table)
    real = mod.collect_video_files
    spy = _recorder(result=real)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(folder))])
    event = QDropEvent(
        QPointF(QPoint(5, 5)), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    )
    with (
        patch.object(mod, "collect_video_files", side_effect=spy),
        qtbot.waitSignal(table.files_dropped, timeout=WAIT_MS) as sig,
    ):
        table.dropEvent(event)
    assert _off_gui(spy.calls)
    assert [Path(p).name for p in sig.args[0]] == ["a.mp4"]
