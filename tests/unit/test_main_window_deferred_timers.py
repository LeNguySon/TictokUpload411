"""Start-up jobs scheduled by the main window (fingerprint backfill, dialog prewarm) belong to the window.

Plain ``QTimer.singleShot`` lambdas outlived closed windows: in the test suite they fired 119 times inside LATER
tests (78 prewarms building 9 dialogs each for dead windows, on deleted temp databases, SQLite on the GUI thread),
which made the GUI-thread tests flaky and crashed CI with an access violation.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QApplication
from src.application.workers.task_worker import drain_ui_tasks
from src.infrastructure.database.migrations.runner import run_all_migrations


@pytest.fixture
def make_window(qapp, tmp_path: Path):
    from src.presentation.views.main_window import TikTokManagerMainWindow

    windows = []

    def make(stagger_ms: int = 5):
        db = tmp_path / f"mw{len(windows)}.db"
        run_all_migrations(db)
        with (
            patch("src.presentation.views.main_window.MetricsSyncWorker"),
            patch("src.presentation.views.main_window.SamMonnyDaemonSupervisor"),
            patch("src.presentation.views.main_window.setTheme"),
            patch.object(TikTokManagerMainWindow, "BACKFILL_DELAY_MS", 30),
            patch.object(TikTokManagerMainWindow, "PREWARM_DELAY_MS", 40),
        ):
            win = TikTokManagerMainWindow(db_path=db)
        win.PREWARM_STAGGER_MS = stagger_ms  # read at every prewarm step (no event was processed yet)
        win.scheduler_timer.stop()
        win.profile_status_timer.stop()
        drain_ui_tasks()
        windows.append(win)
        return win

    yield make
    for win in windows:
        win.close()
        win.deleteLater()
    QApplication.processEvents()


def test_startup_jobs_run_while_the_window_is_open(make_window, qtbot):
    from src.presentation.views.main_window import TikTokManagerMainWindow

    with patch.object(TikTokManagerMainWindow, "_backfill_fingerprints") as backfill:
        win = make_window()
        qtbot.waitUntil(lambda: backfill.called, timeout=2000)
    qtbot.waitUntil(lambda: len(win._dialogs._dialogs) == len(win._dialog_factories()), timeout=3000)


def test_closed_window_runs_no_startup_job(make_window, qtbot):
    from src.presentation.views.main_window import TikTokManagerMainWindow

    with patch.object(TikTokManagerMainWindow, "_backfill_fingerprints") as backfill, patch.object(
        TikTokManagerMainWindow, "_dialog_factories"
    ) as factories:
        win = make_window()
        win.close()
        qtbot.wait(300)
    assert not backfill.called
    assert not factories.called


def test_prewarm_stops_when_the_window_closes_midway(make_window, qtbot):
    win = make_window(stagger_ms=150)
    qtbot.waitUntil(lambda: len(win._dialogs._dialogs) >= 1, timeout=2000)
    win.close()
    built = len(win._dialogs._dialogs)
    qtbot.wait(200)
    assert len(win._dialogs._dialogs) == built < len(win._dialog_factories())
