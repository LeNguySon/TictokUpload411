"""UI responsiveness Sprint P0 (T1-T4) — see docs/03_work_breakdown/ui_responsiveness_fix_plan.md.

T1: Fluent tables repaint only the rows whose hover/pressed/selected state changed.
T2: id -> row lookups are O(1) and stay correct after sorting.
T3: profile_updated patches the affected rows (coalesced) instead of rebuilding the whole table.
T4: upload signals are rate-limited; runtime status deltas are persisted off the GUI thread.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QEvent, QObject, QRect
from PyQt6.QtGui import QRegion
from PyQt6.QtWidgets import QApplication, QTableWidgetItem

_WIDGETS: list = []


def _keep(widget):
    """Tracks top-level widgets so they are torn down with deleteLater() (GC-deleting a shown
    Fluent TableWidget crashes PyQt — pre-existing qfluentwidgets behaviour)."""
    _WIDGETS.append(widget)
    return widget


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app
    while _WIDGETS:
        w = _WIDGETS.pop()
        w.close()
        w.deleteLater()
    app.processEvents()


# ---------------------------------------------------------------------------
# T1 — Fast table: partial repaints
# ---------------------------------------------------------------------------
class _PaintSpy(QObject):
    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)  # owned by the table: never outlives the viewport it filters
        self.region = QRegion()

    def eventFilter(self, obj, event):  # noqa: N802 - Qt API
        if event.type() == QEvent.Type.Paint:
            self.region = self.region.united(event.region())
        return False


def _make_fast_table(qapp, rows: int = 60, cols: int = 6):
    from src.presentation.widgets.fast_table import FastTableWidget

    table = _keep(FastTableWidget())
    table.setColumnCount(cols)
    table.setRowCount(rows)
    for r in range(rows):
        for c in range(cols):
            table.setItem(r, c, QTableWidgetItem(f"{r}:{c}"))
    table.resize(800, 600)
    table.show()
    qapp.processEvents()
    spy = _PaintSpy(table)
    table.viewport().installEventFilter(spy)
    return table, spy


def _painted_rows(table, region: QRegion) -> set[int]:
    width = table.viewport().width()
    painted = set()
    for r in range(table.rowCount()):
        y = table.rowViewportPosition(r)
        if y < 0 or y > table.viewport().height():
            continue
        if region.intersects(QRect(0, y + 1, width, table.rowHeight(r) - 2)):
            painted.add(r)
    return painted


def _repaint_after(qapp, spy, action) -> QRegion:
    qapp.processEvents()
    spy.region = QRegion()
    action()
    qapp.processEvents()
    return spy.region


def test_hover_change_repaints_only_old_and_new_rows(qapp):
    table, spy = _make_fast_table(qapp)
    table._setHoverRow(3)
    region = _repaint_after(qapp, spy, lambda: table._setHoverRow(7))
    assert _painted_rows(table, region) == {3, 7}
    assert table.delegate.hoverRow == 7


def test_hover_leave_repaints_only_previous_row(qapp):
    table, spy = _make_fast_table(qapp)
    table._setHoverRow(5)
    region = _repaint_after(qapp, spy, lambda: table._setHoverRow(-1))
    assert _painted_rows(table, region) == {5}


def test_pressed_row_repaints_only_affected_rows(qapp):
    table, spy = _make_fast_table(qapp)
    table._setPressedRow(2)
    region = _repaint_after(qapp, spy, lambda: table._setPressedRow(9))
    assert _painted_rows(table, region) == {2, 9}


def test_selection_change_repaints_only_changed_rows(qapp):
    table, spy = _make_fast_table(qapp)
    table.selectRow(2)
    region = _repaint_after(qapp, spy, lambda: table.selectRow(9))
    assert _painted_rows(table, region) == {2, 9}
    assert table.delegate.selectedRows == {9}


def test_selection_tracking_does_not_enumerate_every_cell(qapp):
    """selectedIndexes() is O(rows x cols); the fast table must derive rows from selection ranges."""
    table, _ = _make_fast_table(qapp, rows=40)

    def _boom():
        raise AssertionError("selectedIndexes() must not be used for row-state tracking")

    table.selectedIndexes = _boom
    table.selectRow(4)
    assert table.delegate.selectedRows == {4}
    table.selectAll()
    assert table.delegate.selectedRows == set(range(40))
    table.clearSelection()
    assert table.delegate.selectedRows == set()


def test_main_tables_use_fast_table(qapp):
    from src.presentation.widgets.fast_table import FastTableItemDelegate, FastTableWidget
    from src.presentation.widgets.profile_table_widget import ProfileTableWidget
    from src.presentation.widgets.video_queue_table_widget import VideoQueueTableWidget

    assert issubclass(ProfileTableWidget, FastTableWidget)
    assert issubclass(VideoQueueTableWidget, FastTableWidget)
    assert isinstance(_keep(ProfileTableWidget()).delegate, FastTableItemDelegate)


# ---------------------------------------------------------------------------
# T2 — O(1) id -> row lookup
# ---------------------------------------------------------------------------
def _profiles(n: int) -> list[dict]:
    return [{"id": i, "name": f"P{i:03d}", "status": "stopped", "uuid": f"u-{i}"} for i in range(1, n + 1)]


def _videos(n: int) -> list[dict]:
    return [{"id": i, "file_name": f"v{i:03d}.mp4", "status": "available"} for i in range(1, n + 1)]


def test_video_row_lookup_is_constant_time_and_survives_sorting(qapp):
    from PyQt6.QtCore import Qt
    from src.presentation.widgets.video_queue_table_widget import VideoQueueTableWidget

    table = _keep(VideoQueueTableWidget())
    table.load_videos(_videos(200))
    table.sortItems(1, Qt.SortOrder.DescendingOrder)

    with patch.object(table, "rowCount", side_effect=AssertionError("lookup must not scan rows")):
        row = table.find_row_by_video_id(150)
    assert table.item(row, 0).data(256)["id"] == 150  # Qt.ItemDataRole.UserRole == 256
    assert table.find_row_by_video_id(9999) is None


def test_profile_row_lookup_is_constant_time_and_survives_sorting(qapp):
    from PyQt6.QtCore import Qt
    from src.presentation.widgets.profile_table_widget import ProfileTableWidget

    table = _keep(ProfileTableWidget())
    table.load_profiles(_profiles(120))
    table.sortItems(2, Qt.SortOrder.DescendingOrder)

    with patch.object(table, "rowCount", side_effect=AssertionError("lookup must not scan rows")):
        row = table.row_for_profile_id(17)
    assert table.item(row, 0).data(Qt.ItemDataRole.UserRole)["id"] == 17
    assert table.row_for_profile_id(9999) is None


def test_video_progress_update_does_not_scan_rows(qapp):
    from src.presentation.widgets.video_queue_table_widget import VideoQueueTableWidget

    table = _keep(VideoQueueTableWidget())
    table.load_videos(_videos(200))
    with patch.object(table, "rowCount", side_effect=AssertionError("must not scan rows")):
        table.update_progress(200, 42.0)
        table.append_log(200, "00:00", "CHUNK", "chunk 1")
        table.update_stage(200, "Đang gửi 42%")
    assert "42%" in table.item(table.find_row_by_video_id(200), 9).text()


# ---------------------------------------------------------------------------
# T3 / T4 — main window behaviour
# ---------------------------------------------------------------------------
@pytest.fixture
def main_window(qapp, tmp_path: Path):
    from src.infrastructure.database.migrations.runner import run_all_migrations
    from src.infrastructure.database.repositories.profile_repository import ProfileRepository

    db_file = tmp_path / "p0.db"
    run_all_migrations(db_file)
    repo = ProfileRepository(db_file)
    ids = [repo.create({"name": f"Profile_{i}", "uuid": f"uuid-p0-{i:04d}", "status": "stopped"}) for i in range(1, 11)]

    with (
        patch("src.presentation.views.main_window.MetricsSyncWorker"),
        patch("src.presentation.views.main_window.SamMonnyDaemonSupervisor"),
        patch("src.presentation.views.main_window.setTheme"),
    ):
        from src.presentation.views.main_window import TikTokManagerMainWindow

        win = TikTokManagerMainWindow(db_path=db_file)
        win.scheduler_timer.stop()
        win.profile_status_timer.stop()
        yield win, ids
        win.close()
        win.deleteLater()
        qapp.processEvents()


def test_profile_updated_burst_is_coalesced_into_row_patches(main_window):
    win, ids = main_window
    win._profile_patch_timer.stop()

    with (
        patch.object(win.profile_repo, "list_active", side_effect=AssertionError("no DB reload")),
        patch.object(win.profile_table, "load_profiles", side_effect=AssertionError("no table rebuild")),
        patch.object(win, "_trigger_async_status_sync") as status_sync,
    ):
        for i, pid in enumerate(ids[:5]):
            win.signal_bus.profile_updated.emit(pid, {"username_on_tiktok": f"tt_user_{i}"})
            win.signal_bus.profile_updated.emit(pid, {"followers": 1000 + i})
        QApplication.processEvents()
        assert win._profile_patch_timer.isActive(), "patches must be coalesced by a single-shot timer"

        with patch.object(win.profile_table, "update_profile_row", wraps=win.profile_table.update_profile_row) as upd:
            win._flush_profile_patches()
        assert upd.call_count == 5
        status_sync.assert_not_called()

    row = win.profile_table.row_for_profile_id(ids[0])
    assert win.profile_table.item(row, 6).text() == "tt_user_0"
    prof = win.profile_table.item(row, 0).data(256)
    assert prof["followers"] == 1000 and prof["username_on_tiktok"] == "tt_user_0"


def test_profile_updated_for_unknown_or_trashed_profile_falls_back_to_one_refresh(main_window):
    win, ids = main_window
    win._profile_patch_timer.stop()
    with patch.object(win, "refresh_profiles") as refresh:
        win.signal_bus.profile_updated.emit(99999, {"name": "new"})
        win.signal_bus.profile_updated.emit(ids[0], {"is_trashed": 1})
        QApplication.processEvents()
        win._flush_profile_patches()
    refresh.assert_called_once()


def test_status_delta_slot_updates_cells_without_touching_db(main_window):
    win, ids = main_window
    with (
        patch.object(win.profile_repo, "update", side_effect=AssertionError("GUI slot must not write DB")),
        patch.object(win.profile_repo, "bulk_update_fields", side_effect=AssertionError("GUI slot must not write DB")),
    ):
        win._on_profile_statuses_updated({ids[2]: "running"})
    row = win.profile_table.row_for_profile_id(ids[2])
    assert win.profile_table.item(row, 12).text() == "running"


def test_runtime_sync_worker_persists_deltas_before_emitting(qapp):
    from src.application.workers.profile_runtime_sync_worker import ProfileRuntimeSyncWorker

    launcher = MagicMock()
    launcher.batch_check_profiles_running.return_value = {1: True, 2: True, 3: False}
    repo = MagicMock()
    profiles = [
        {"id": 1, "status": "stopped"},
        {"id": 2, "status": "stopped"},
        {"id": 3, "status": "running", "username_on_tiktok": "x"},
    ]
    worker = ProfileRuntimeSyncWorker(profiles=profiles, launcher=launcher, profile_repo=repo)
    received = []
    worker.signals.statuses_updated.connect(received.append)
    worker.execute()

    calls = {tuple(sorted(c.args[0])): c.args[1] for c in repo.bulk_update_fields.call_args_list}
    assert calls == {(1, 2): {"status": "running"}, (3,): {"status": "LIVE"}}
    assert received == [{1: "running", 2: "running", 3: "LIVE"}]


def test_main_window_passes_repo_to_runtime_sync_worker(main_window):
    win, _ = main_window
    with patch("src.application.workers.profile_runtime_sync_worker.ProfileRuntimeSyncWorker") as worker_cls:
        win._is_status_sync_running = False
        win._trigger_async_status_sync([{"id": 1, "status": "stopped"}], force=True)
    assert worker_cls.call_args.kwargs["profile_repo"] is win.profile_repo


class _FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def _upload_worker(clock):
    from src.application.signals.app_signals import AppSignalBus
    from src.application.workers.upload_worker import UploadWorker

    bus = AppSignalBus()
    worker = UploadWorker(video_id=7, profile_id=1, upload_service=MagicMock(), signal_bus=bus, clock=clock)
    progress, stages = [], []
    bus.upload_progress.connect(lambda *a: progress.append(a))
    bus.upload_stage_changed.connect(lambda *a: stages.append(a))
    return worker, progress, stages


def test_upload_progress_burst_is_rate_limited_but_keeps_final_100(qapp):
    clock = _FakeClock()
    worker, progress, stages = _upload_worker(clock)
    total = 1000
    for i in range(1, total + 1):  # 1000 chunk callbacks at the same instant
        worker._on_progress(i, total, i * 100.0 / total)

    assert len(progress) <= 3, f"burst must be throttled, got {len(progress)} progress signals"
    assert len(stages) <= 3
    assert progress[-1][3] == 100.0
    assert "100%" in stages[-1][1]


def test_upload_progress_emits_again_after_throttle_interval(qapp):
    clock = _FakeClock()
    worker, progress, _ = _upload_worker(clock)
    for pct in (10.0, 20.0, 30.0):
        worker._on_progress(int(pct), 100, pct)
        clock.t += 0.3
    assert [p[3] for p in progress] == [10.0, 20.0, 30.0]
