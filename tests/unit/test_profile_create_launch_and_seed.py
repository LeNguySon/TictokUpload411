"""Create 1 profile, bulk create, launch with cookies, open profile folder — regression tests.

Defects found on 2026-11-06:
1. Bulk add assigned every row the LAST proxy in the table (wrong proxy for existing / duplicate
   proxies, and some random proxy for an unparsable proxy line).
2. The offline fallback of add / bulk add generated the uuid twice: an orphan empty folder per profile.
3. Every launch re-wrote the imported cookies with INSERT OR REPLACE, overwriting the session the
   browser had refreshed (could log the account out).
4. The SDK launch path (tried first) never seeded the cookies, so a new profile opened logged-out.
5. "Mở Thư Mục Hồ Sơ" created a folder for whatever it was given: it could open an empty new folder
   and the "does not exist" warning could never show.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from src.infrastructure.browser.cookie_injector import BrowserCookieInjector
from src.infrastructure.browser.orbita_launcher import OrbitaLauncher
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository

COOKIE = "sessionid=imported111; sid_tt=imported111; tt_csrf_token=abc"


def _cookie_value(profile_dir: Path, name: str) -> str | None:
    db = Path(profile_dir) / "Default" / "Network" / "Cookies"
    if not db.exists():
        return None
    row = sqlite3.connect(db).execute("SELECT value FROM cookies WHERE name = ?", (name,)).fetchone()
    return row[0] if row else None


def _browser_refreshes_session(profile_dir: Path, value: str) -> None:
    db = Path(profile_dir) / "Default" / "Network" / "Cookies"
    conn = sqlite3.connect(db)
    conn.execute("UPDATE cookies SET value = ? WHERE name = 'sessionid'", (value,))
    conn.commit()
    conn.close()


@pytest.fixture
def daemon_dir(tmp_path, monkeypatch):
    d = tmp_path / "daemon_profiles"
    d.mkdir()
    monkeypatch.setattr("src.infrastructure.browser.orbita_launcher.daemon_profiles_dir", lambda: d)
    monkeypatch.setattr(OrbitaLauncher, "DAEMON_PROFILES_DIR", d)
    return d


@pytest.fixture
def repos(tmp_path):
    db = tmp_path / "app.db"
    run_all_migrations(db)
    return ProfileRepository(db), ProjectRepository(db), ProxyRepository(db)


@pytest.fixture
def offline_daemon():
    """The SamMonny daemon is not running: dialogs take their offline fallback."""
    with patch(
        "src.application.services.gologin_sync_service.GoLoginSyncService.create_real_gologin_profile",
        side_effect=ConnectionError("daemon offline"),
    ):
        yield


# ---------------------------------------------------------------- 1. bulk proxy assignment
def test_proxy_import_line_returns_the_id_of_that_proxy(repos):
    _, _, proxy_repo = repos
    first = proxy_repo.import_line("1.1.1.1:8001:u1:p1")
    second = proxy_repo.import_line("2.2.2.2:8002:u2:p2")
    assert first != second
    assert proxy_repo.import_line("1.1.1.1:8001:u1:p1") == first  # existing proxy is reused
    assert proxy_repo.get_by_id(first)["host"] == "1.1.1.1"
    assert proxy_repo.import_line("not a proxy") is None


def test_bulk_add_gives_each_row_its_own_proxy(qtbot, repos, daemon_dir, offline_daemon):
    from src.presentation.dialogs.bulk_add_profile_dialog import BulkAddProfileDialog

    profile_repo, project_repo, proxy_repo = repos
    proxy_repo.import_line("1.1.1.1:8001:u1:p1")  # already in the table before the import
    rows = [
        {"user": "acc_a", "proxy": "1.1.1.1:8001:u1:p1"},
        {"user": "acc_b", "proxy": "3.3.3.3:8003:u3:p3"},
        {"user": "acc_c", "proxy": "garbage-proxy"},
        {"user": "acc_d"},
    ]
    dlg = BulkAddProfileDialog(profile_repo, project_repo, proxy_repo)
    qtbot.addWidget(dlg)
    with patch.object(dlg, "_get_parsed_rows", return_value=rows), patch(
        "src.presentation.dialogs.bulk_add_profile_dialog.InfoBar"
    ):
        dlg._on_import_all()

    by_name = {p["name"]: p for p in profile_repo.list_all()}
    host = {px["id"]: px["host"] for px in proxy_repo.list_all()}
    assert host[by_name["acc_a"]["proxy_id"]] == "1.1.1.1"
    assert host[by_name["acc_b"]["proxy_id"]] == "3.3.3.3"
    assert by_name["acc_c"]["proxy_id"] is None  # never a random proxy
    assert by_name["acc_d"]["proxy_id"] is None


# ---------------------------------------------------------------- 2. one folder per profile
def test_add_one_profile_offline_creates_exactly_one_folder_with_cookies(qtbot, repos, daemon_dir, offline_daemon):
    from src.presentation.dialogs.add_profile_dialog import AddProfileDialog

    profile_repo, project_repo, proxy_repo = repos
    dlg = AddProfileDialog(profile_repo=profile_repo, project_repo=project_repo, proxy_repo=proxy_repo, vault=MagicMock())
    qtbot.addWidget(dlg)
    dlg.name_input.setText("Acc One")
    dlg.cookie_input.setPlainText(COOKIE)
    dlg._on_save()

    [profile] = profile_repo.list_all()
    folders = [p for p in daemon_dir.iterdir() if p.is_dir()]
    assert folders == [Path(profile["storage_dir"])]
    assert _cookie_value(folders[0], "sessionid") == "imported111"


def test_bulk_add_offline_creates_one_folder_per_profile(qtbot, repos, daemon_dir, offline_daemon):
    from src.presentation.dialogs.bulk_add_profile_dialog import BulkAddProfileDialog

    profile_repo, project_repo, proxy_repo = repos
    dlg = BulkAddProfileDialog(profile_repo, project_repo, proxy_repo)
    qtbot.addWidget(dlg)
    rows = [{"user": f"bulk_{i}", "cookie": COOKIE} for i in range(3)]
    with patch.object(dlg, "_get_parsed_rows", return_value=rows), patch(
        "src.presentation.dialogs.bulk_add_profile_dialog.InfoBar"
    ):
        dlg._on_import_all()

    profiles = profile_repo.list_all()
    folders = sorted(p for p in daemon_dir.iterdir() if p.is_dir())
    assert len(profiles) == 3 and folders == sorted(Path(p["storage_dir"]) for p in profiles)
    assert all(_cookie_value(f, "sessionid") == "imported111" for f in folders)


# ---------------------------------------------------------------- 3. seed once, never clobber
def test_seed_cookies_once_then_browser_owns_them(tmp_path):
    prof = tmp_path / "p"
    assert BrowserCookieInjector.seed_profile_cookies(prof, COOKIE) is True
    _browser_refreshes_session(prof, "refreshed999")
    assert BrowserCookieInjector.seed_profile_cookies(prof, COOKIE) is False
    assert _cookie_value(prof, "sessionid") == "refreshed999"
    # The user edits the profile's cookies: the new cookies are applied once.
    assert BrowserCookieInjector.seed_profile_cookies(prof, "sessionid=newimport222") is True
    assert _cookie_value(prof, "sessionid") == "newimport222"


def test_seed_marker_does_not_store_the_cookie(tmp_path):
    prof = tmp_path / "p"
    BrowserCookieInjector.seed_profile_cookies(prof, COOKIE)
    marker = prof / BrowserCookieInjector.SEED_MARKER
    assert marker.exists() and "imported111" not in marker.read_text(encoding="utf-8")


def test_relaunch_keeps_refreshed_browser_session(tmp_path):
    launcher = OrbitaLauncher(executable_path=tmp_path / "chrome.exe")
    profile = {"id": 1, "name": "P", "storage_dir": str(tmp_path / "p1"), "cookies_json": COOKIE}
    launcher.prepare_profile_environment(tmp_path / "p1", profile)
    assert _cookie_value(tmp_path / "p1", "sessionid") == "imported111"
    _browser_refreshes_session(tmp_path / "p1", "refreshed999")
    launcher.prepare_profile_environment(tmp_path / "p1", profile)  # second launch
    assert _cookie_value(tmp_path / "p1", "sessionid") == "refreshed999"


# ---------------------------------------------------------------- 4. SDK launch seeds cookies
def test_sdk_launch_seeds_cookies_before_start(tmp_path, daemon_dir):
    launcher = OrbitaLauncher(executable_path=tmp_path / "chrome.exe")
    seen_at_start: dict = {}

    class FakeGoLogin:
        def __init__(self, opts):
            self.opts = opts

        def post_cookies(self, items, profile_id=None):
            seen_at_start["posted"] = len(items)
            return True

        def start(self):
            seen_at_start["sqlite"] = _cookie_value(daemon_dir / "uuid-sdk-1", "sessionid")
            return "127.0.0.1:9222"

    with patch("sammonny.gologin.gologin.GoLogin", FakeGoLogin):
        addr = launcher.launch_via_gologin_sdk(profile_id="uuid-sdk-1", cookie_raw=COOKIE)
    assert addr == "127.0.0.1:9222"
    assert seen_at_start == {"sqlite": "imported111", "posted": 3}


def test_launch_worker_hands_cookies_to_sdk_launch():
    from PyQt6.QtWidgets import QApplication
    from src.application.workers.orbita_launch_worker import OrbitaLaunchWorker

    QApplication.instance() or QApplication([])
    profile = {"id": 5, "name": "C", "uuid": "u5", "direct_connection": 1, "cookies_json": COOKIE}
    profile_repo, proxy_repo, launcher = MagicMock(), MagicMock(), MagicMock()
    profile_repo.get_by_id.return_value = profile
    launcher.launch_via_gologin_sdk.return_value = "127.0.0.1:1"
    OrbitaLaunchWorker([5], profile_repo, proxy_repo, orbita_launcher=launcher).run()
    assert launcher.launch_via_gologin_sdk.call_args.kwargs["cookie_raw"] == COOKIE


# ---------------------------------------------------------------- 5. open profile folder
def test_locate_profile_dir_never_creates_folders(tmp_path, daemon_dir):
    missing = {"uuid": "uuid-missing", "name": "Ghost", "storage_dir": str(tmp_path / "nowhere")}
    assert OrbitaLauncher.locate_profile_dir(missing) is None
    assert not (tmp_path / "nowhere").exists() and not (daemon_dir / "uuid-missing").exists()

    real = daemon_dir / "uuid-real"
    real.mkdir()
    assert OrbitaLauncher.locate_profile_dir({"uuid": "uuid-real", "storage_dir": "profiles/x"}) == real


def _window(tmp_path):
    db = tmp_path / "mw.db"
    run_all_migrations(db)
    with (
        patch("src.presentation.views.main_window.MetricsSyncWorker"),
        patch("src.presentation.views.main_window.SamMonnyDaemonSupervisor"),
    ):
        from src.presentation.views.main_window import TikTokManagerMainWindow

        win = TikTokManagerMainWindow(db_path=db)
    win.scheduler_timer.stop()
    win.profile_status_timer.stop()
    return win


def test_context_menu_opens_the_profiles_real_folder(qtbot, tmp_path, daemon_dir):
    win = _window(tmp_path)
    qtbot.addWidget(win)
    real = daemon_dir / "uuid-open-1"
    real.mkdir()
    pid = win.profile_repo.create({"name": "Open", "uuid": "uuid-open-1", "storage_dir": str(real)})
    with patch("src.presentation.views.main_window.os.startfile", create=True) as startfile:
        win.profile_table.open_profile_folder_requested.emit(pid)
    startfile.assert_called_once_with(str(real))


def test_context_menu_warns_when_profile_has_no_folder_and_creates_nothing(qtbot, tmp_path, daemon_dir):
    win = _window(tmp_path)
    qtbot.addWidget(win)
    gone = tmp_path / "deleted_profile"
    pid = win.profile_repo.create({"name": "Gone", "uuid": "uuid-gone-1", "storage_dir": str(gone)})
    with (
        patch("src.presentation.views.main_window.os.startfile", create=True) as startfile,
        patch("src.presentation.views.main_window.InfoBar") as info,
    ):
        win.profile_table.open_profile_folder_requested.emit(pid)
    startfile.assert_not_called()
    info.warning.assert_called_once()
    assert not gone.exists() and not (daemon_dir / "uuid-gone-1").exists()
