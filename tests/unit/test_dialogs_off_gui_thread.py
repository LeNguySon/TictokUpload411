"""
AccountHealthDialog, ChannelRadarDialog and TrashDialog must not touch SQLite on the GUI thread
(AGENTS.md: every DB query runs on a QThreadPool), and a background result arriving after the
dialog was destroyed must be dropped instead of crashing (access violation seen in the suite).
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from src.application.workers.task_worker import drain_ui_tasks
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository


@pytest.fixture
def health_db(tmp_path: Path) -> dict:
    db_file = tmp_path / "health.db"
    run_all_migrations(db_file)
    repo = ProfileRepository(db_file)
    pid = repo.create({"name": "HealthTarget", "status": "LIVE"})
    conn = sqlite3.connect(db_file)
    conn.execute(
        "INSERT INTO violateVideos (profile_id, video_id, title, violate_title, appeal_date, status) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (pid, "111", "Clip", "Gậy Nguyên Tác", "2026-12-01", "pending"),
    )
    conn.execute("UPDATE profiles SET account_standing='Warning', strike_count=1 WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return {"db_file": db_file, "repo": repo, "pid": pid}


def _record_connect_threads():
    """Patches sqlite3.connect to record which threads open connections."""
    threads: list[str] = []
    real_connect = sqlite3.connect

    def spy(*args, **kwargs):
        threads.append(threading.current_thread().name)
        return real_connect(*args, **kwargs)

    return threads, patch("sqlite3.connect", side_effect=spy)


# ---------------------------------------------------------------- AccountHealthDialog


def test_fetch_health_data_is_pure_and_reads_profile_violations_appeals(health_db) -> None:
    from src.presentation.dialogs.account_health_dialog import fetch_health_data

    data = fetch_health_data(health_db["db_file"], health_db["pid"])
    assert data is not None
    assert data["profile"]["account_standing"] == "Warning"
    assert [v["video_id"] for v in data["violations"]] == ["111"]
    assert data["appeals"] == []
    assert fetch_health_data(health_db["db_file"], 99999) is None


def test_account_health_dialog_loads_off_gui_thread(health_db, qtbot) -> None:
    from src.presentation.dialogs.account_health_dialog import AccountHealthDialog

    threads, spy = _record_connect_threads()
    with spy:
        dialog = AccountHealthDialog(profile_id=health_db["pid"], db_path=health_db["db_file"])
        qtbot.addWidget(dialog)
        assert drain_ui_tasks()

    assert threads, "the dialog never read the database"
    assert threading.main_thread().name not in threads
    assert dialog.table_violate.rowCount() == 1
    assert dialog.card_standing.value_label.text() == "Warning"


def test_account_health_result_after_dialog_destroyed_is_dropped(health_db, qapp) -> None:
    from src.presentation.dialogs.account_health_dialog import AccountHealthDialog

    dialog = AccountHealthDialog(profile_id=health_db["pid"], db_path=health_db["db_file"])
    assert drain_ui_tasks()
    dialog.table_violate.selectRow(0)

    release = threading.Event()

    def slow_appeal(*_args):
        release.wait(5)
        return {"ok": True}

    with patch.object(dialog.moderation_service, "submit_video_appeal", side_effect=slow_appeal):
        dialog._on_appeal_selected_video(mock_reason="Bản quyền chính chủ")
        dialog.close()
        dialog.deleteLater()
        qapp.sendPostedEvents(None, 0)  # deliver DeferredDelete: the C++ dialog is gone
        qapp.processEvents()
        release.set()
        assert drain_ui_tasks()  # the late result must be ignored, not crash


# ---------------------------------------------------------------- ChannelRadarDialog


def test_load_radar_inputs_returns_profile_and_videos(health_db) -> None:
    from src.presentation.dialogs.channel_radar_dialog import load_radar_inputs

    profile, videos = load_radar_inputs(health_db["repo"], health_db["db_file"], health_db["pid"])
    assert profile["name"] == "HealthTarget"
    assert isinstance(videos, list)


def test_channel_radar_dialog_with_preloaded_data_does_not_query_db(health_db, qtbot) -> None:
    from src.presentation.dialogs.channel_radar_dialog import ChannelRadarDialog

    threads, spy = _record_connect_threads()
    with spy:
        dialog = ChannelRadarDialog(
            profile_id=health_db["pid"],
            profile_repo=health_db["repo"],
            profile={"name": "Preloaded", "total_followers": 10, "views_month": 100},
            videos=[],
            db_path=health_db["db_file"],
        )
        qtbot.addWidget(dialog)
    assert threads == []


# ---------------------------------------------------------------- TrashDialog


def test_trash_dialog_lists_off_gui_thread(health_db, qtbot) -> None:
    from src.presentation.dialogs.trash_dialog import TrashDialog

    repo: ProfileRepository = health_db["repo"]
    repo.update(health_db["pid"], is_trashed=1)

    threads, spy = _record_connect_threads()
    with spy:
        dialog = TrashDialog(profile_repo=repo)
        qtbot.addWidget(dialog)
        assert drain_ui_tasks()

    assert threads and threading.main_thread().name not in threads
    assert dialog.table.rowCount() == 1


def test_trash_empty_requires_confirmation(health_db, qtbot) -> None:
    from src.presentation.dialogs import trash_dialog

    repo: ProfileRepository = health_db["repo"]
    repo.update(health_db["pid"], is_trashed=1)
    dialog = trash_dialog.TrashDialog(profile_repo=repo)
    qtbot.addWidget(dialog)
    assert drain_ui_tasks()

    with patch.object(trash_dialog, "confirm_permanent_delete", return_value=False):
        dialog._on_empty_trash()
        assert drain_ui_tasks()
    assert repo.get_by_id(health_db["pid"]) is not None  # declined: nothing deleted

    with patch.object(trash_dialog, "confirm_permanent_delete", return_value=True):
        dialog._on_empty_trash()
        assert drain_ui_tasks()
    assert repo.get_by_id(health_db["pid"]) is None
    assert dialog.table.rowCount() == 0
