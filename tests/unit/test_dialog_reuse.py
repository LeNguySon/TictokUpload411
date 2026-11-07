"""
Opening a dialog froze the GUI 60-240 ms. Measured: creating a NEW top-level window costs 45-110 ms of native
Windows work by itself (a bare QDialog, any Qt platform option), while re-showing an existing hidden dialog takes
~0.2 ms. Parameterless dialogs are therefore created once (or pre-warmed when idle) and re-shown; each one resets
what must not leak between openings in prepare_reopen().
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog
from src.application.workers.task_worker import drain_ui_tasks
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
from src.presentation.dialogs.dialog_cache import DialogCache


@pytest.fixture
def repos(tmp_path: Path):
    db = tmp_path / "reuse.db"
    run_all_migrations(db)
    return ProfileRepository(db), ProjectRepository(db), ProxyRepository(db)


class _Probe(QDialog):
    def __init__(self) -> None:
        super().__init__()
        self.reopened: list[dict] = []

    def prepare_reopen(self, **kwargs) -> None:
        self.reopened.append(kwargs)


def test_cache_reuses_the_instance_and_resets_it_on_reopen(qtbot) -> None:
    cache = DialogCache()
    first = cache.get("probe", _Probe)
    qtbot.addWidget(first)
    assert first.reopened == []  # a fresh dialog needs no reset
    again = cache.get("probe", _Probe, value=7)
    assert again is first and first.reopened == [{"value": 7}]


def test_cache_recreates_a_deleted_dialog(qtbot, qapp) -> None:
    cache = DialogCache()
    first = cache.get("probe", _Probe)
    from PyQt6 import sip

    sip.delete(first)  # the C++ dialog is gone (e.g. closed with WA_DeleteOnClose)
    second = cache.get("probe", _Probe)
    qtbot.addWidget(second)
    assert second is not first and second.reopened == []


def test_prewarm_creates_the_native_window_without_showing(qtbot) -> None:
    cache = DialogCache()
    cache.prewarm("probe", _Probe)
    dlg = cache.get("probe", _Probe)
    qtbot.addWidget(dlg)
    assert dlg.testAttribute(Qt.WidgetAttribute.WA_WState_Created) and not dlg.isVisible()
    assert dlg.reopened == [{}]  # handed out after a prewarm: brought up to date


def test_trash_reopen_reloads_and_accepts_results_again(qtbot, repos) -> None:
    from src.presentation.dialogs.trash_dialog import TrashDialog

    profiles, _, _ = repos
    dlg = TrashDialog(profile_repo=profiles)
    qtbot.addWidget(dlg)
    assert drain_ui_tasks()
    dlg.done(0)  # closed: late results are ignored
    pid = profiles.create({"name": "trashed later"})
    profiles.update(pid, is_trashed=1)
    dlg.prepare_reopen()
    assert drain_ui_tasks()
    assert dlg.table.rowCount() == 1


def test_proxy_manager_reopen_reconnects_signals_once(qtbot, repos) -> None:
    from src.presentation.dialogs.proxy_dialog import ProxyManagerDialog

    _, _, proxies = repos
    dlg = ProxyManagerDialog(proxy_repo=proxies, proxy_service=MagicMock())
    qtbot.addWidget(dlg)
    assert drain_ui_tasks()
    dlg.reject()  # disconnects the bus signals
    dlg.prepare_reopen()
    dlg.prepare_reopen()
    with patch.object(dlg, "_schedule_refresh") as refresh:
        dlg.signal_bus.proxy_checked.emit(1, True, 10.0, "alive")
    assert refresh.call_count == 1  # connected again, exactly once
    dlg.reject()


def test_table_settings_reopen_shows_current_hidden_columns(qtbot) -> None:
    from src.presentation.dialogs.table_settings_dialog import TableSettingsDialog

    dlg = TableSettingsDialog(hidden_columns={1})
    qtbot.addWidget(dlg)
    dlg.prepare_reopen(hidden_columns={2})
    assert dlg._checkboxes[1].isChecked() and not dlg._checkboxes[2].isChecked()
    assert dlg.hidden_columns == {2}


def test_secret_inputs_are_cleared_on_reopen(qtbot) -> None:
    from src.presentation.dialogs.api_cookie_dialog import ApiCookieDialog
    from src.presentation.dialogs.permissions_dialog import PermissionsDialog

    api = ApiCookieDialog(vault=MagicMock())
    qtbot.addWidget(api)
    api.txt_client_secret.setText("secret_fake")
    api.txt_cookies.setPlainText("sessionid=fake")
    api.prepare_reopen()
    assert api.txt_client_secret.text() == "" and api.txt_cookies.toPlainText() == ""

    perm = PermissionsDialog()
    qtbot.addWidget(perm)
    perm.txt_auth_code.setText("code_fake")
    perm.prepare_reopen()
    assert perm.txt_auth_code.text() == ""


def test_sync_transfer_reopen_lists_new_projects(qtbot, repos) -> None:
    from src.presentation.dialogs.sync_transfer_dialog import SyncTransferDialog

    profiles, projects, proxies = repos
    dlg = SyncTransferDialog(projects, profiles, proxies)
    qtbot.addWidget(dlg)
    projects.create(name="Dự án mới sau khi mở")
    dlg.prepare_reopen()
    texts = [dlg.combo_project_export.itemText(i) for i in range(dlg.combo_project_export.count())]
    assert "Dự án mới sau khi mở" in texts


def test_project_manager_reopen_refreshes(qtbot, repos) -> None:
    from src.presentation.dialogs.project_dialog import ProjectManagerDialog

    _, projects, _ = repos
    dlg = ProjectManagerDialog(projects)
    qtbot.addWidget(dlg)
    with patch.object(dlg, "refresh_projects") as refresh:
        dlg.prepare_reopen()
    refresh.assert_called_once()


def test_upload_settings_reopen_reloads_stored_values(qtbot, tmp_path: Path) -> None:
    from dataclasses import replace

    from PyQt6.QtCore import QSettings
    from src.application.settings.upload_settings import UploadMethod, load_upload_settings, save_upload_settings
    from src.presentation.dialogs.upload_settings_dialog import UploadSettingsDialog

    store = QSettings(str(tmp_path / "upload.ini"), QSettings.Format.IniFormat)
    dlg = UploadSettingsDialog(store=store)
    qtbot.addWidget(dlg)
    save_upload_settings(replace(load_upload_settings(store), method=UploadMethod.OFFICIAL), store)
    on_saved = MagicMock()
    dlg.prepare_reopen(on_saved=on_saved)
    assert dlg.on_saved is on_saved
    assert dlg.cmb_method.currentData() == UploadMethod.OFFICIAL.value
