"""The profile table must render the real `profiles` DB columns.

It used to read keys that do not exist in the schema (t_follows, t_views, t_video, earned, qg,
kyc, note, re_apply, views_30d, cookie), so those columns always showed 0 / empty for profiles
loaded from SQLite. Legacy alias keys are still accepted as a fallback.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def _cells(table, row: int) -> dict[int, str]:
    return {c: (table.item(row, c).text() if table.item(row, c) else "") for c in range(table.columnCount())}


def test_profile_table_renders_db_columns(qapp, qtbot, tmp_path: Path):
    from src.presentation.widgets.profile_table_widget import ProfileTableWidget

    db = tmp_path / "cols.db"
    run_all_migrations(db)
    repo = ProfileRepository(db)
    pid = repo.create({"name": "Metrics", "uuid": "uuid-cols-0001"})
    repo.update(
        pid,
        total_followers=12500,
        total_views=3400000,
        total_videos=42,
        views_month=98000,
        money_earned=123.45,
        country="VN",
        state_kyc="Yes",
        notes="ghi chú",
        date_reapply="2026-12-01",
        cookies_json="sessionid=abcdef1234567890",
    )

    table = ProfileTableWidget()
    qtbot.addWidget(table)
    table.load_profiles(repo.list_active())
    cells = _cells(table, table.row_for_profile_id(pid))

    assert cells[7] not in ("", "0"), "Views(30d) <- views_month"
    assert cells[8] not in ("", "0"), "T.Follows <- total_followers"
    assert cells[9] not in ("", "0"), "T.Views <- total_views"
    assert cells[10] == "42", "T.Video <- total_videos"
    assert "123" in cells[14], "$Earned <- money_earned"
    assert cells[18] == "VN", "QG <- country"
    assert cells[19] == "Yes", "KYC <- state_kyc"
    assert cells[20] == "ghi chú", "Note <- notes"
    assert cells[21] == "2026-12-01", "Re.Apply <- date_reapply"
    assert cells[13] not in ("", "sessionid=abcdef1234567890"), "Cookie <- cookies_json, masked"
    assert cells[3] == "Yes", "Logged <- stored cookies (cookies_json / cookies_browser)"


def test_profile_table_keeps_legacy_alias_keys(qapp, qtbot):
    from src.presentation.widgets.profile_table_widget import ProfileTableWidget

    table = ProfileTableWidget()
    qtbot.addWidget(table)
    table.load_profiles(
        [{"id": 1, "name": "Legacy", "t_follows": 777, "t_video": 5, "qg": "JP", "kyc": "No", "note": "x"}]
    )
    cells = _cells(table, 0)
    assert cells[8] == "777" and cells[10] == "5" and cells[18] == "JP" and cells[20] == "x"


def _edit_dialog(repo: ProfileRepository, db: Path, pid: int):
    from unittest.mock import MagicMock

    from src.infrastructure.database.repositories.project_repository import ProjectRepository
    from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
    from src.presentation.dialogs.add_profile_dialog import AddProfileDialog

    return AddProfileDialog(
        profile_repo=repo,
        project_repo=ProjectRepository(db),
        proxy_repo=ProxyRepository(db),
        vault=MagicMock(),
        profile_data=repo.get_by_id(pid),
    )


def test_edit_dialog_shows_and_saves_stored_cookie(qapp, qtbot, tmp_path: Path):
    db = tmp_path / "edit.db"
    run_all_migrations(db)
    repo = ProfileRepository(db)
    pid = repo.create({"name": "Edit", "uuid": "uuid-edit-0001", "status": "stopped"})
    repo.update(pid, cookies_json="sessionid=OLD")

    dlg = _edit_dialog(repo, db, pid)
    qtbot.addWidget(dlg)
    assert dlg.cookie_input.toPlainText() == "sessionid=OLD", "edit dialog must show the stored cookie"

    dlg.cookie_input.setPlainText("sessionid=NEW")
    dlg._on_save()
    assert repo.get_by_id(pid)["cookies_json"] == "sessionid=NEW", "an edited cookie must be persisted"


def test_edit_dialog_without_cookie_change_keeps_cookies_and_status(qapp, qtbot, tmp_path: Path):
    db = tmp_path / "keep.db"
    run_all_migrations(db)
    repo = ProfileRepository(db)
    pid = repo.create({"name": "Keep", "uuid": "uuid-keep-0001", "status": "DIE"})
    repo.update(pid, cookies_json="sessionid=A", cookies_browser="sessionid=B")

    dlg = _edit_dialog(repo, db, pid)
    qtbot.addWidget(dlg)
    dlg.name_input.setText("Keep renamed")
    dlg._on_save()

    row = repo.get_by_id(pid)
    assert row["name"] == "Keep renamed"
    assert row["cookies_json"] == "sessionid=A" and row["cookies_browser"] == "sessionid=B"
    assert row["status"] == "DIE", "renaming must not flip the status to LIVE"


def test_runtime_status_counts_db_cookie_columns_as_logged_in(qapp):
    from unittest.mock import MagicMock

    from src.application.workers.profile_runtime_sync_worker import ProfileRuntimeSyncWorker

    launcher = MagicMock()
    launcher.batch_check_profiles_running.return_value = {1: False}
    worker = ProfileRuntimeSyncWorker(
        profiles=[{"id": 1, "status": "running", "cookies_json": "sessionid=x"}], launcher=launcher
    )
    got = []
    worker.signals.statuses_updated.connect(got.append)
    worker.execute()
    assert got == [{1: "LIVE"}]
