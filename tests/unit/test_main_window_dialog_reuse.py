"""Main-window menu dialogs are reused (DialogCache) instead of being rebuilt on every click."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QApplication, QDialog
from qfluentwidgets import MessageBox
from src.application.workers.task_worker import drain_ui_tasks
from src.infrastructure.database.migrations.runner import run_all_migrations

HANDLERS = [
    "_on_open_project_manager", "_on_open_proxy_manager", "_on_api_cookie", "_on_permissions", "_on_send_recv",
    "_on_table_cfg", "_on_guide", "_on_open_trash", "_on_upload_settings",
]


@pytest.fixture
def window(qapp, tmp_path: Path):
    db = tmp_path / "mw.db"
    run_all_migrations(db)
    with (
        patch("src.presentation.views.main_window.MetricsSyncWorker"),
        patch("src.presentation.views.main_window.SamMonnyDaemonSupervisor"),
        patch("src.presentation.views.main_window.setTheme"),
    ):
        from src.presentation.views.main_window import TikTokManagerMainWindow

        win = TikTokManagerMainWindow(db_path=db)
    win.scheduler_timer.stop()
    win.profile_status_timer.stop()
    assert drain_ui_tasks()
    yield win
    win.close()
    win.deleteLater()
    QApplication.processEvents()


@pytest.mark.parametrize("handler", HANDLERS)
def test_menu_dialog_is_created_once_and_reused(window, handler: str) -> None:
    opened: list[QDialog] = []

    def fake_exec(dlg, *a, **k):
        opened.append(dlg)
        return 0

    with patch.object(QDialog, "exec", fake_exec), patch.object(MessageBox, "exec", fake_exec):
        getattr(window, handler)()
        getattr(window, handler)()
        assert drain_ui_tasks()
    dialogs = [d for d in opened if not isinstance(d, MessageBox)]
    assert len(dialogs) == 2 and dialogs[0] is dialogs[1]


def test_table_settings_reused_with_current_hidden_columns(window) -> None:
    seen: list[set] = []
    with patch.object(QDialog, "exec", lambda dlg, *a, **k: seen.append(set(dlg.hidden_columns)) or 0):
        window.hidden_columns = {3}
        window._on_table_cfg()
        window.hidden_columns = {5}
        window._on_table_cfg()
    assert seen == [{3}, {5}]


def test_menu_dialogs_are_prewarmed_when_idle(window) -> None:
    with patch.object(window._dialogs, "prewarm") as prewarm:
        window._prewarm_dialogs()
    keys = {c.args[0] for c in prewarm.call_args_list}
    assert {"proxy_manager", "project_manager", "trash"} <= keys


ONE_SHOT = [
    ("_on_add_profile", ()), ("_on_bulk_add_profiles", ()), ("_on_open_batch_folder_upload", ()),
    ("_on_soft_delete_profiles", ([1],)), ("_on_regenerate_fingerprints", ([1],)),
]


@pytest.mark.parametrize(("handler", "args"), ONE_SHOT)
def test_one_shot_dialogs_do_not_pile_up_as_hidden_children(window, qapp, handler: str, args: tuple) -> None:
    """Every opening used to leave the closed dialog alive as a hidden child of the main window (27 hidden
    dialogs after 36 openings), each a full widget tree with Fluent event filters."""
    from PyQt6.QtCore import QEvent

    def count() -> int:
        qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        qapp.processEvents()
        return len([d for d in window.findChildren(QDialog) if not d.isVisible()])

    before = count()
    with patch.object(QDialog, "exec", lambda dlg, *a, **k: 0), patch.object(MessageBox, "exec", lambda dlg, *a, **k: 0):
        for _ in range(3):
            getattr(window, handler)(*args)
            assert drain_ui_tasks()
    assert count() <= before + 1  # only the last finished dialog is kept (until the next one opens)
