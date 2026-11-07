"""
The 15 s upload scheduler read AND wrote SQLite (list_scheduled_due + try_reserve) on the GUI thread; with an
upload writing at the same time it could block up to busy_timeout (10 s) on every tick. The DB part now runs on
the UI pool; only worker creation/dispatch stays on the GUI thread.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication
from src.application.workers.task_worker import drain_ui_tasks
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.video_repository import VideoRepository


def _due_video(db: Path, n: int, profile_id: int | None) -> int:
    repo = VideoRepository(db)
    vid = repo.register_or_update(
        video_hash=f"hash_due_{n}", file_path=f"C:/v/{n}.mp4", file_name=f"v{n}", file_size=10, mtime=1.0
    )
    repo.update_schedule(vid, schedule_time="2026-01-01 10:00:00", assigned_profile_id=profile_id)
    return vid


@pytest.fixture
def window(qapp, tmp_path: Path):
    db = tmp_path / "sched.db"
    run_all_migrations(db)
    ProfileRepository(db).create({"name": "P1", "uuid": "uuid-s-1", "status": "stopped"})
    with (
        patch("src.presentation.views.main_window.MetricsSyncWorker"),
        patch("src.presentation.views.main_window.SamMonnyDaemonSupervisor"),
        patch("src.presentation.views.main_window.setTheme"),
    ):
        from src.presentation.views.main_window import TikTokManagerMainWindow

        win = TikTokManagerMainWindow(db_path=db)
    win.scheduler_timer.stop()
    win.profile_status_timer.stop()
    win._trigger_async_status_sync = MagicMock()
    assert drain_ui_tasks()
    yield win, db
    win.close()
    win.deleteLater()
    QApplication.processEvents()


def test_reserve_due_videos_reserves_and_round_robins(tmp_path: Path) -> None:
    from src.presentation.views.main_window import reserve_due_videos

    db = tmp_path / "r.db"
    run_all_migrations(db)
    profiles = ProfileRepository(db)
    p_assigned, p_sel1, p_sel2 = (profiles.create({"name": f"P{i}", "status": "stopped"}) for i in range(3))
    a = _due_video(db, 1, profile_id=p_assigned)
    b = _due_video(db, 2, profile_id=None)
    c = _due_video(db, 3, profile_id=None)
    repo = VideoRepository(db)

    pairs = reserve_due_videos(repo, "2026-06-01 00:00:00", fallback_profile_ids=[p_sel1, p_sel2])
    # Round-robin index = videos dispatched so far (assigned ones included), as before the refactor.
    assert pairs == [(a, p_assigned), (b, p_sel2), (c, p_sel1)]
    assert reserve_due_videos(repo, "2026-06-01 00:00:00", fallback_profile_ids=[p_sel1]) == []  # already reserved


def test_scheduler_tick_does_no_sqlite_on_gui_thread_and_dispatches(window) -> None:
    from src.application.workers.upload_worker import UploadWorker

    win, db = window
    _due_video(db, 1, profile_id=1)
    threads: list[str] = []
    real_connect = sqlite3.connect

    def spy(*a, **k):
        threads.append(threading.current_thread().name)
        return real_connect(*a, **k)

    with (
        patch("sqlite3.connect", side_effect=spy),
        patch.object(win.thread_pool, "dispatch_upload") as up,
        patch.object(win, "refresh_videos"),
    ):
        win._check_scheduled_queue()
        assert threading.main_thread().name not in threads  # nothing on the GUI thread
        assert drain_ui_tasks()

    assert threads
    assert threading.main_thread().name not in threads
    assert up.call_count == 1 and isinstance(up.call_args.args[0], UploadWorker)


def test_scheduler_tick_is_single_flight(window) -> None:
    win, _ = window
    with patch.object(win, "_run_bg") as run_bg:
        win._check_scheduled_queue()
        win._check_scheduled_queue()  # previous check still in flight: skipped
    assert run_bg.call_count == 1
