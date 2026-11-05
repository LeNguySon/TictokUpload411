"""Profiles deliberately run WITHOUT a proxy (host IP) must launch; accidental no-proxy stays blocked.

The fail-closed gate (bf9ce45) refused every profile without proxy/VPN, including the ones the user
intentionally runs from the machine's own IP. A per-profile opt-in ``direct_connection`` now allows
exactly those; a missing proxy without the opt-in, a leak-flagged or dead proxy are still refused.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from src.application.workers.orbita_launch_worker import OrbitaLaunchWorker
from src.infrastructure.browser.orbita_launcher import OrbitaLauncher
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository


@pytest.fixture
def qapp():
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def repo(tmp_path):
    db = tmp_path / "direct.db"
    run_all_migrations(db)
    return ProfileRepository(db)


def _worker(profile, proxy=None, alive=True):
    profile_repo, proxy_repo, launcher = MagicMock(), MagicMock(), MagicMock()
    profile_repo.get_by_id.return_value = profile
    proxy_repo.get_by_id.return_value = proxy
    launcher.launch_via_gologin_sdk.return_value = None  # fall through to the binary launch
    launcher.launch_profile.return_value = MagicMock(pid=4321)
    worker = OrbitaLaunchWorker([profile["id"]], profile_repo, proxy_repo, orbita_launcher=launcher)
    failed, launched = [], []
    worker.signals.profile_failed.connect(lambda *a: failed.append(a))
    worker.signals.profile_launched.connect(lambda *a: launched.append(a))
    with patch.object(type(worker), "_check_proxy_alive", return_value=alive):
        worker.run()
    return launcher, failed, launched


# --- storage
def test_migration_adds_direct_connection_default_off(repo):
    pid = repo.create({"name": "A", "uuid": "uuid-direct-0001"})
    assert repo.get_by_id(pid)["direct_connection"] == 0


def test_set_direct_connection_clears_proxy_and_vpn(repo):
    pid = repo.create({"name": "A", "uuid": "uuid-direct-0002"})
    repo.bulk_update_fields([pid], {"proxy_id": None, "vpn_config": "[Interface]"})
    assert repo.set_direct_connection([pid]) == 1
    p = repo.get_by_id(pid)
    assert p["direct_connection"] == 1 and p["proxy_id"] is None and p["vpn_config"] is None


def test_assigning_a_proxy_turns_direct_mode_off(repo):
    from src.infrastructure.database.repositories.proxy_repository import ProxyRepository

    pid = repo.create({"name": "A", "uuid": "uuid-direct-0003"})
    repo.set_direct_connection([pid])
    proxy_id = ProxyRepository(repo.db_path).create(host="1.2.3.4", port=8080)
    repo.bulk_assign_proxy([pid], proxy_id)
    assert repo.get_by_id(pid)["direct_connection"] == 0  # losing that proxy later must not leak silently


# --- launch worker gate
def test_worker_launches_direct_profile_without_proxy(qapp):
    launcher, failed, launched = _worker({"id": 7, "name": "Direct", "uuid": "u7", "direct_connection": 1})
    assert not failed and launched
    launcher.launch_profile.assert_called_once()
    assert launcher.launch_profile.call_args.args[1] is None
    assert launcher.launch_via_gologin_sdk.call_args.kwargs.get("direct_connection") is True


def test_worker_still_refuses_accidental_no_proxy_and_explains_opt_in(qapp):
    launcher, failed, _ = _worker({"id": 8, "name": "Lost", "uuid": "u8", "direct_connection": 0})
    launcher.launch_profile.assert_not_called()
    assert "Chạy không proxy" in failed[0][2]


def test_direct_flag_does_not_bypass_dead_or_leaking_proxy(qapp):
    profile = {"id": 9, "name": "D", "uuid": "u9", "direct_connection": 1, "proxy_id": 3}
    launcher, failed, _ = _worker(profile, {"id": 3, "host": "1.2.3.4", "port": 80, "status": "active"}, alive=False)
    launcher.launch_profile.assert_not_called() and failed
    launcher, failed, _ = _worker(profile, {"id": 3, "host": "1.2.3.4", "port": 80, "status": "leak_detected"})
    launcher.launch_profile.assert_not_called()
    assert failed


# --- launcher
def test_launcher_runs_direct_profile_without_proxy_args(tmp_path):
    launcher = OrbitaLauncher(executable_path=tmp_path / "chrome.exe")
    profile = {"id": 77, "name": "Direct", "storage_dir": str(tmp_path / "p77"), "direct_connection": 1}
    with patch("subprocess.Popen") as popen, patch.object(launcher.supervisor, "create_lock"):
        launcher.launch_profile(profile)
    args = popen.call_args.args[0]
    assert not any(a.startswith(("--proxy-server", "--host-resolver-rules")) for a in args)


def test_launcher_still_refuses_no_proxy_without_opt_in(tmp_path):
    launcher = OrbitaLauncher(executable_path=tmp_path / "chrome.exe")
    with patch("subprocess.Popen", side_effect=AssertionError("started from host IP")):
        with pytest.raises(PermissionError):
            launcher.launch_profile({"id": 78, "name": "X", "storage_dir": str(tmp_path / "p78")})


def test_sdk_launch_of_direct_profile_clears_stale_daemon_proxy(tmp_path, monkeypatch):
    launcher = OrbitaLauncher(executable_path=tmp_path / "chrome.exe")
    monkeypatch.setattr(OrbitaLauncher, "DAEMON_PROFILES_DIR", tmp_path / "daemon")
    pref = tmp_path / "daemon" / "u77" / "Default" / "Preferences"
    pref.parent.mkdir(parents=True)
    pref.write_text(json.dumps({"gologin": {"proxy": {"mode": "fixed_servers", "server": "http://old:1"}}}))
    with patch.object(OrbitaLauncher, "_sdk_start", return_value=None, create=True):
        try:
            launcher.launch_via_gologin_sdk(profile_id="u77", proxy_data=None, direct_connection=True)
        except Exception:
            pass  # no daemon in tests; only the Preferences sync matters
    assert json.loads(pref.read_text())["gologin"]["proxy"] == {"mode": "none"}


# --- UI
def test_table_shows_direct_profiles(qtbot):
    from src.presentation.widgets.profile_table_widget import ProfileTableWidget

    table = ProfileTableWidget()
    qtbot.addWidget(table)
    table.load_profiles([{"id": 1, "name": "A", "uuid": "u", "direct_connection": 1}])
    assert "IP máy" in table.item(0, 4).text()


def test_assign_proxy_dialog_offers_direct_mode(qtbot, repo):
    from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
    from src.presentation.dialogs.assign_proxy_dialog import AssignProxyDialog

    pid = repo.create({"name": "A", "uuid": "uuid-direct-0004"})
    dlg = AssignProxyDialog(profile_ids=[pid], profile_repo=repo, proxy_repo=ProxyRepository(repo.db_path))
    qtbot.addWidget(dlg)
    idx = dlg.combo_proxy.findData(AssignProxyDialog.DIRECT_CONNECTION)
    assert idx >= 0 and "IP máy" in dlg.combo_proxy.itemText(idx)
    dlg.combo_proxy.setCurrentIndex(idx)
    dlg._on_apply()
    assert repo.get_by_id(pid)["direct_connection"] == 1


def test_context_menu_direct_mode_needs_confirmation(qtbot, tmp_path):
    db = tmp_path / "mw.db"
    run_all_migrations(db)
    pid = ProfileRepository(db).create({"name": "A", "uuid": "uuid-direct-0005"})
    with (
        patch("src.presentation.views.main_window.MetricsSyncWorker"),
        patch("src.presentation.views.main_window.SamMonnyDaemonSupervisor"),
    ):
        from src.presentation.views.main_window import TikTokManagerMainWindow

        win = TikTokManagerMainWindow(db_path=db)
    win.scheduler_timer.stop()
    win.profile_status_timer.stop()
    qtbot.addWidget(win)
    with patch("src.presentation.views.main_window.MessageBox") as box:
        box.return_value.exec.return_value = False
        win._on_direct_connection_selected([pid])
        assert win.profile_repo.get_by_id(pid)["direct_connection"] == 0
        box.return_value.exec.return_value = True
        win._on_direct_connection_selected([pid])
    assert win.profile_repo.get_by_id(pid)["direct_connection"] == 1
    assert Path(db).exists()
