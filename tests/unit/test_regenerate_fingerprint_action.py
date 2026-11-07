"""
Right-click > Quản Lý Hồ Sơ > "Cập Nhật Vân Tay Trình Duyệt": gives the selected profiles a NEW fixed fingerprint.
The daemon record is updated through PUT /api/v1/profiles/{id}/fingerprint (SamMonny >= 1.8.5) so SDK launches
and the app's own Preferences stay identical; running profiles are skipped.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PyQt6.QtGui import QContextMenuEvent
from src.application.services.gologin_sync_service import regenerate_fingerprints
from src.domain.fingerprint.browser_fingerprint import generate_fingerprint
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository

NEW_FP = generate_fingerprint("fresh-daemon-fingerprint")


@pytest.fixture
def repo(tmp_path: Path) -> ProfileRepository:
    db = tmp_path / "regen.db"
    run_all_migrations(db)
    return ProfileRepository(db)


def _fp(repo: ProfileRepository, pid: int) -> dict:
    return json.loads(repo.get_by_id(pid)["fingerprint_json"])


def test_daemon_profile_gets_the_daemons_new_fingerprint(repo: ProfileRepository) -> None:
    pid = repo.create({"name": "d", "uuid": "uuid-d"})
    client = MagicMock()
    client.update_fingerprint.return_value = NEW_FP
    summary = regenerate_fingerprints(repo, [pid], client)
    client.update_fingerprint.assert_called_once_with("uuid-d", regenerate=True)
    assert summary.daemon == [pid] and not summary.failed
    assert _fp(repo, pid) == NEW_FP
    assert repo.get_by_id(pid)["user_agent"] == NEW_FP["navigator"]["user_agent"]


def test_profile_without_daemon_record_gets_a_new_local_fingerprint(repo: ProfileRepository) -> None:
    pid = repo.create({"name": "l", "uuid": "uuid-l"})
    old = _fp(repo, pid)
    client = MagicMock()
    client.update_fingerprint.side_effect = RuntimeError("HTTP 404 Error: Profile 'uuid-l' not found")
    client.get_profile.return_value = None  # no daemon record
    summary = regenerate_fingerprints(repo, [pid], client)
    assert summary.local == [pid]
    new = _fp(repo, pid)
    assert new != old and new["canvas_noise"] != old["canvas_noise"]


def test_running_profiles_are_skipped(repo: ProfileRepository) -> None:
    pid = repo.create({"name": "r", "uuid": "uuid-r", "status": "running"})
    old = _fp(repo, pid)
    client = MagicMock()
    summary = regenerate_fingerprints(repo, [pid], client)
    assert summary.skipped_running == [pid]
    client.update_fingerprint.assert_not_called()
    assert _fp(repo, pid) == old


def test_daemon_record_that_cannot_be_updated_is_left_unchanged(repo: ProfileRepository) -> None:
    """Old daemon (no endpoint) but the record exists: changing only the app copy would make SDK launches and
    direct launches use different fingerprints, so nothing is changed and the profile is reported."""
    pid = repo.create({"name": "o", "uuid": "uuid-o"})
    old = _fp(repo, pid)
    client = MagicMock()
    client.update_fingerprint.side_effect = RuntimeError("HTTP 405 Method Not Allowed")
    client.get_profile.return_value = MagicMock(raw_data={"fingerprint": old})
    summary = regenerate_fingerprints(repo, [pid], client)
    assert [f[0] for f in summary.failed] == [pid]
    assert _fp(repo, pid) == old


def test_context_menu_offers_fingerprint_update_and_emits_ids(qapp, monkeypatch) -> None:
    from src.presentation.widgets.profile_table_widget import ProfileTableWidget

    widget = ProfileTableWidget()
    widget.load_profiles([{"id": 7, "name": "A", "status": "stopped"}, {"id": 8, "name": "B", "status": "stopped"}])
    widget.selectAll()
    captured: dict = {}
    monkeypatch.setattr("qfluentwidgets.RoundMenu.exec", lambda menu, *a, **k: captured.setdefault("menu", menu))
    rect = widget.visualRect(widget.model().index(0, 0))
    widget.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Reason.Mouse, rect.center(), widget.mapToGlobal(rect.center())))

    def walk(menu):
        acts = list(menu.actions())
        for sub in getattr(menu, "_subMenus", []):
            acts += walk(sub)
        return acts

    action = next(a for a in walk(captured["menu"]) if "Vân Tay" in a.text())
    emitted: list = []
    widget.regenerate_fingerprint_requested.connect(emitted.append)
    action.trigger()
    assert sorted(emitted[0]) == [7, 8]


def test_window_confirms_then_regenerates_off_the_gui_thread(qapp, tmp_path: Path) -> None:
    import threading
    from unittest.mock import patch

    from PyQt6.QtWidgets import QApplication
    from src.application.services.gologin_sync_service import FingerprintUpdateSummary
    from src.application.workers.task_worker import drain_ui_tasks

    db = tmp_path / "win.db"
    run_all_migrations(db)
    with (
        patch("src.presentation.views.main_window.MetricsSyncWorker"),
        patch("src.presentation.views.main_window.SamMonnyDaemonSupervisor"),
        patch("src.presentation.views.main_window.setTheme"),
    ):
        from src.presentation.views import main_window as mw

        win = mw.TikTokManagerMainWindow(db_path=db)
    win.scheduler_timer.stop()
    win.profile_status_timer.stop()
    assert drain_ui_tasks()
    threads: list[str] = []

    def fake_regen(repo, ids, client):
        threads.append(threading.current_thread().name)
        return FingerprintUpdateSummary(daemon=list(ids))

    try:
        with patch.object(mw, "regenerate_fingerprints", side_effect=fake_regen) as regen, patch.object(
            win, "_confirm_regenerate_fingerprints", return_value=False
        ):
            win._on_regenerate_fingerprints([1, 2])
            assert drain_ui_tasks()
        regen.assert_not_called()  # declined

        with (
            patch.object(mw, "regenerate_fingerprints", side_effect=fake_regen),
            patch.object(win, "_confirm_regenerate_fingerprints", return_value=True),
            patch.object(mw, "InfoBar") as info,
        ):
            win._on_regenerate_fingerprints([1, 2])
            assert drain_ui_tasks()
        assert threads and threading.main_thread().name not in threads
        assert "2 hồ sơ" in info.success.call_args.kwargs["content"]
    finally:
        win.close()
        win.deleteLater()
        QApplication.processEvents()
