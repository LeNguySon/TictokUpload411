"""UI responsiveness Sprint P2 (T8-T10) — see docs/03_work_breakdown/ui_responsiveness_fix_plan.md.

T8: uploads run on their own pool, so short UI/support workers never queue behind them.
T9: psutil process scans are single-flight (one process_iter at a time, results shared).
T10: search filters are debounced, missing avatars are negatively cached, upload notifications
     are aggregated.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QThreadPool
from PyQt6.QtWidgets import QApplication
from src.application.workers.task_worker import drain_ui_tasks

WAIT_MS = 5000


class _Blocker:
    """Worker body that blocks until released."""

    def __init__(self) -> None:
        self.release = threading.Event()
        self.started = threading.Semaphore(0)

    def __call__(self) -> None:
        self.started.release()
        self.release.wait(10)


def _worker(fn):
    from src.application.workers.base_worker import BaseWorker

    class _W(BaseWorker):
        def execute(self) -> None:
            fn()

    return _W()


# ---------------------------------------------------------------------------
# T8 — dedicated upload pool
# ---------------------------------------------------------------------------
def test_upload_pool_is_separate_and_follows_concurrency_setting(qapp):
    from src.application.workers.thread_pool_manager import ThreadPoolManager

    mgr = ThreadPoolManager.instance()
    assert mgr.upload_pool is not QThreadPool.globalInstance()
    mgr.set_max_threads(3)
    assert mgr.upload_pool.maxThreadCount() == 3
    assert mgr.max_upload_threads == 3
    mgr.set_max_threads(10)


def test_saturated_upload_pool_does_not_block_short_workers(qapp, qtbot):
    from src.application.workers.thread_pool_manager import ThreadPoolManager

    mgr = ThreadPoolManager.instance()
    mgr.set_max_threads(2)
    blocker = _Blocker()
    try:
        for _ in range(4):  # 2 running + 2 queued uploads
            mgr.dispatch_upload(_worker(blocker))
        assert blocker.started.acquire(timeout=5) and blocker.started.acquire(timeout=5)

        ran = threading.Event()
        mgr.dispatch(_worker(ran.set))
        assert ran.wait(3), "a short worker must not wait behind long uploads"
    finally:
        blocker.release.set()
        mgr.upload_pool.waitForDone(5000)
        mgr.set_max_threads(10)  # pools are process-wide: restore defaults for other tests


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def main_window(qapp, tmp_path: Path):
    from src.infrastructure.database.migrations.runner import run_all_migrations
    from src.infrastructure.database.repositories.profile_repository import ProfileRepository

    db_file = tmp_path / "p2.db"
    run_all_migrations(db_file)
    repo = ProfileRepository(db_file)
    for i, email in enumerate(["alpha@x.com", "beta@x.com", "gamma@x.com"], start=1):
        repo.create({"name": f"Profile_{i}", "uuid": f"uuid-p2-{i:04d}", "status": "stopped", "email": email})

    with (
        patch("src.presentation.views.main_window.MetricsSyncWorker"),
        patch("src.presentation.views.main_window.SamMonnyDaemonSupervisor"),
        patch("src.presentation.views.main_window.setTheme"),
    ):
        from src.presentation.views.main_window import TikTokManagerMainWindow

        win = TikTokManagerMainWindow(db_path=db_file)
        win.scheduler_timer.stop()
        win.profile_status_timer.stop()
        win._trigger_async_status_sync = MagicMock()
        yield win
        win.close()
        win.deleteLater()
        QApplication.processEvents()


def test_scheduled_uploads_are_dispatched_to_upload_pool(main_window):
    from src.application.workers.upload_worker import UploadWorker

    win = main_window
    with (
        patch.object(win.video_repo, "list_scheduled_due", return_value=[{"id": 11, "assigned_profile_id": 1}]),
        patch.object(win.video_repo, "try_reserve", return_value=True),
        patch.object(win.thread_pool, "dispatch_upload") as up,
        patch.object(win.thread_pool, "dispatch") as general,
        patch.object(win, "refresh_videos"),
    ):
        win._check_scheduled_queue()
        assert drain_ui_tasks()  # reservation runs off the GUI thread
    assert up.call_count == 1 and isinstance(up.call_args.args[0], UploadWorker)
    assert not any(isinstance(c.args[0], UploadWorker) for c in general.call_args_list)


def test_main_window_never_sends_upload_workers_to_general_pool():
    """Static guard: every UploadWorker created in main_window goes through dispatch_upload()."""
    src = Path("src/presentation/views/main_window.py").read_text(encoding="utf-8")
    blocks = src.split("UploadWorker(")[1:]
    assert blocks
    for block in blocks:
        head = block[:600]
        assert "dispatch_upload(" in head and "thread_pool.dispatch(worker)" not in head.split("dispatch_upload(")[0]


# ---------------------------------------------------------------------------
# T9 — single-flight psutil scan
# ---------------------------------------------------------------------------
def test_concurrent_psutil_scans_are_single_flight(qapp):
    from src.application.workers.task_worker import drain_ui_tasks
    from src.infrastructure.browser import orbita_launcher as mod
    from src.infrastructure.browser.orbita_launcher import OrbitaLauncher

    # The cache is process-wide and background status-sync workers from earlier tests may still be
    # scanning: let every pool go idle, then start cold.
    drain_ui_tasks()
    QThreadPool.globalInstance().waitForDone(5000)
    mod._PSUTIL_SCAN_CACHE["time"] = float("-inf")
    launchers = [OrbitaLauncher(executable_path=Path("C:/dummy/chrome.exe")) for _ in range(2)]
    state = {"active": 0, "max_active": 0, "calls": 0}
    lock = threading.Lock()

    def fake_process_iter(attrs):
        with lock:
            state["active"] += 1
            state["calls"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
        time.sleep(0.1)
        with lock:
            state["active"] -= 1
        return iter([])

    fake_psutil = MagicMock()
    fake_psutil.process_iter.side_effect = fake_process_iter
    with patch.dict("sys.modules", {"psutil": fake_psutil}):
        threads = [
            threading.Thread(target=launchers[i % 2]._scan_psutil_for_profile, kwargs={"uuid_val": f"uuid-{i:010d}"})
            for i in range(6)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(5)

    assert state["max_active"] == 1, "psutil.process_iter must never run concurrently (Windows access violation)"
    assert state["calls"] <= 2, "callers arriving during a scan must reuse its fresh result"


def test_psutil_is_a_declared_dependency():
    req = Path("requirements.txt").read_text(encoding="utf-8")
    proj = Path("pyproject.toml").read_text(encoding="utf-8")
    assert "psutil" in req and "psutil" in proj


# ---------------------------------------------------------------------------
# T10 — debounced search, avatar negative cache, aggregated notifications
# ---------------------------------------------------------------------------
def _visible_rows(table) -> int:
    return sum(1 for r in range(table.rowCount()) if not table.isRowHidden(r))


def test_profile_search_is_debounced(main_window, qtbot):
    win = main_window
    with patch.object(win, "_apply_profile_filter", wraps=win._apply_profile_filter) as apply_filter:
        for partial in ("b", "be", "bet", "beta"):
            win.search_profile.setText(partial)
        assert apply_filter.call_count == 0, "filtering must wait until typing pauses"
        qtbot.waitUntil(lambda: apply_filter.call_count == 1, timeout=WAIT_MS)
    assert _visible_rows(win.profile_table) == 1


def test_video_search_is_debounced(main_window, qtbot):
    win = main_window
    with patch.object(win, "_apply_video_filter", wraps=win._apply_video_filter) as apply_filter:
        for partial in ("x", "xy", "xyz"):
            win.search_video.setText(partial)
        assert apply_filter.call_count == 0
        qtbot.waitUntil(lambda: apply_filter.call_count == 1, timeout=WAIT_MS)


def test_missing_avatar_lookup_is_cached(tmp_path: Path):
    from src.presentation.delegates import circular_avatar_delegate as mod

    missing = str(tmp_path / "nope.jpg")
    mod.clear_avatar_cache()
    with patch.object(mod.Path, "is_file", autospec=True, return_value=False) as is_file:
        for _ in range(50):
            assert mod.get_cached_avatar_pixmap(missing, 32) is None
    assert is_file.call_count == 1


def test_missing_avatar_is_rechecked_after_ttl(tmp_path: Path):
    from src.presentation.delegates import circular_avatar_delegate as mod

    missing = str(tmp_path / "later.jpg")
    mod.clear_avatar_cache()
    clock = [100.0]
    with (
        patch.object(mod.time, "monotonic", side_effect=lambda: clock[0]),
        patch.object(mod.Path, "is_file", autospec=True, return_value=False) as is_file,
    ):
        mod.get_cached_avatar_pixmap(missing, 32)
        clock[0] += mod.MISSING_AVATAR_TTL_S + 1
        mod.get_cached_avatar_pixmap(missing, 32)
    assert is_file.call_count == 2


def test_upload_notifications_are_aggregated(main_window, qtbot):
    win = main_window
    with (
        patch("src.presentation.views.main_window.InfoBar") as info_bar,
        patch.object(win.upload_service, "isolate_video_file", return_value=None),
    ):
        for vid in range(1, 6):
            win._on_upload_completed(vid, f"pub-{vid}")
        win._on_upload_failed(9, "boom")
        win._on_upload_failed(10, "boom")
        assert info_bar.success.call_count == 0 and info_bar.error.call_count == 0
        qtbot.waitUntil(lambda: info_bar.success.called and info_bar.error.called, timeout=WAIT_MS)

    assert info_bar.success.call_count == 1
    assert "5" in info_bar.success.call_args.kwargs["content"]
    assert info_bar.error.call_count == 1
    assert "2" in info_bar.error.call_args.kwargs["content"]


def test_single_upload_notification_keeps_detail(main_window, qtbot):
    win = main_window
    with (
        patch("src.presentation.views.main_window.InfoBar") as info_bar,
        patch.object(win.upload_service, "isolate_video_file", return_value=None),
    ):
        win._on_upload_completed(42, "pub-42")
        qtbot.waitUntil(lambda: info_bar.success.called, timeout=WAIT_MS)
    assert "#42" in info_bar.success.call_args.kwargs["content"]


def test_psutil_scan_reads_cmdline_only_for_browser_processes(qapp):
    """process_iter(["name", "cmdline"]) read every process's command line (~2 s per scan on a
    normal desktop, every 3 s); only chrome/orbita candidates need it."""
    from src.application.workers.task_worker import drain_ui_tasks
    from src.infrastructure.browser import orbita_launcher as mod
    from src.infrastructure.browser.orbita_launcher import OrbitaLauncher

    drain_ui_tasks()
    QThreadPool.globalInstance().waitForDone(5000)
    mod._PSUTIL_SCAN_CACHE["time"] = float("-inf")

    def proc(name, cmdline):
        p = MagicMock()
        p.info = {"name": name}
        p.cmdline.return_value = cmdline
        return p

    procs = [
        proc("explorer.exe", ["explorer.exe"]),
        proc("chrome.exe", ["chrome.exe", "--user-data-dir=C:/profiles/uuid-target-0001"]),
        proc("svchost.exe", ["svchost.exe"]),
    ]
    requested_attrs: list = []
    fake_psutil = MagicMock()
    fake_psutil.process_iter.side_effect = lambda attrs: requested_attrs.append(attrs) or iter(procs)
    with patch.dict("sys.modules", {"psutil": fake_psutil}):
        found = OrbitaLauncher(executable_path=Path("C:/dummy/chrome.exe"))._scan_psutil_for_profile(
            uuid_val="uuid-target-0001"
        )

    assert found is True
    assert all("cmdline" not in attrs for attrs in requested_attrs)
    assert not procs[0].cmdline.called and not procs[2].cmdline.called
    assert procs[1].cmdline.called
