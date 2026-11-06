"""Session renewal: read refreshed cookies from the running browser, prefer them, keep real expiry,
show expiry, and a user-triggered "refresh session" action.

Before: the app only read the cookie SQLite file of a closed browser; Chrome/Orbita encrypt the
cookies they write, so a session TikTok refreshed was never captured and API features kept using the
original imported cookie until it died. JSON cookie expiry was replaced by "+1 year".
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository

DAY = 86400
NOW = 1_800_000_000.0


def _cdp_cookie(name, value, expires, domain=".tiktok.com"):
    return {"name": name, "value": value, "domain": domain, "path": "/", "expires": expires}


@pytest.fixture
def repo(tmp_path):
    db = tmp_path / "s.db"
    run_all_migrations(db)
    return ProfileRepository(db)


# ------------------------------------------------------------------ 1. capture from running browser
def test_summarize_keeps_live_tiktok_cookies_and_session_expiry():
    from src.infrastructure.browser.cdp_session import summarize_tiktok_cookies

    cookies = [
        _cdp_cookie("sessionid", "fresh1", NOW + 50 * DAY),
        _cdp_cookie("sid_tt", "fresh1", NOW + 50 * DAY),
        _cdp_cookie("old", "x", NOW - 10),  # expired: dropped
        _cdp_cookie("ttwid", "w", -1),  # browser-session cookie: kept, no expiry
        _cdp_cookie("NID", "g", NOW + DAY, domain=".google.com"),  # other site: dropped
    ]
    header, expires = summarize_tiktok_cookies(cookies, now=NOW)
    assert header == "sessionid=fresh1; sid_tt=fresh1; ttwid=w"
    assert expires == NOW + 50 * DAY


def test_summarize_without_session_cookie_reports_logged_out():
    from src.infrastructure.browser.cdp_session import summarize_tiktok_cookies

    header, expires = summarize_tiktok_cookies([_cdp_cookie("ttwid", "w", NOW + DAY)], now=NOW)
    assert "sessionid" not in header and expires is None


def test_capture_stores_refreshed_session(repo):
    from src.application.services.cookie_session_service import CookieSessionService

    pid = repo.create({"name": "A", "uuid": "uuid-cap-0001", "cookies_json": "sessionid=old0"})
    fetch = MagicMock(return_value=[_cdp_cookie("sessionid", "fresh1", NOW + 50 * DAY)])
    result = CookieSessionService(repo, fetch=fetch, clock=lambda: NOW).capture(pid, "127.0.0.1:9222")
    p = repo.get_by_id(pid)
    assert result.ok and result.logged_in
    assert p["cookies_browser"] == "sessionid=fresh1"
    assert p["session_expires_at"] == NOW + 50 * DAY and p["cookies_synced_at"]
    assert p["cookies_json"] == "sessionid=old0"  # the user's import is never overwritten
    fetch.assert_called_once_with("127.0.0.1:9222")


def test_capture_when_logged_out_keeps_stored_cookies(repo):
    from src.application.services.cookie_session_service import CookieSessionService

    pid = repo.create({"name": "A", "uuid": "uuid-cap-0002", "cookies_json": "sessionid=old0"})
    repo.update(pid, cookies_browser="sessionid=prev")
    fetch = MagicMock(return_value=[_cdp_cookie("ttwid", "w", NOW + DAY)])
    result = CookieSessionService(repo, fetch=fetch, clock=lambda: NOW).capture(pid, "127.0.0.1:9222")
    assert result.ok and not result.logged_in
    assert repo.get_by_id(pid)["cookies_browser"] == "sessionid=prev"


def test_capture_with_unreachable_browser_fails_softly(repo):
    from src.application.services.cookie_session_service import CookieSessionService

    pid = repo.create({"name": "A", "uuid": "uuid-cap-0003"})
    fetch = MagicMock(side_effect=OSError("connection refused"))
    result = CookieSessionService(repo, fetch=fetch, clock=lambda: NOW).capture(pid, "127.0.0.1:1")
    assert not result.ok and "connection refused" in result.message


# ------------------------------------------------------------------ 2. one source of truth
def test_pick_session_cookie_prefers_browser_cookies():
    from src.domain.policies.cookie_source import pick_session_cookie

    assert pick_session_cookie({"cookies_json": "a=1", "cookies_browser": "b=2"}) == "b=2"
    assert pick_session_cookie({"cookies_json": "a=1"}) == "a=1"
    assert pick_session_cookie({"cookie": "c=3"}) == "c=3"
    assert pick_session_cookie({}) == ""


def test_no_code_prefers_imported_cookies_over_browser_cookies():
    offenders = []
    for py in Path("src").rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        if 'get("cookies_json") or p.get("cookies_browser")' in text or (
            'get("cookie") or p.get("cookies_json")' in text
        ):
            offenders.append(str(py))
    assert offenders == []


def test_new_import_resets_captured_browser_session(repo):
    pid = repo.create({"name": "A", "uuid": "uuid-cap-0004", "cookies_json": "sessionid=old0"})
    repo.update(pid, cookies_browser="sessionid=prev", session_expires_at=NOW, cookies_synced_at="x")
    repo.update(pid, cookies_json="sessionid=newimport")
    p = repo.get_by_id(pid)
    assert p["cookies_browser"] is None and p["cookies_synced_at"] is None
    repo.update(pid, name="renamed")  # unrelated updates keep the captured session
    assert repo.get_by_id(pid)["cookies_json"] == "sessionid=newimport"


# ------------------------------------------------------------------ 3. real JSON expiry
def _json_cookies(session_exp):
    return json.dumps(
        [
            {"name": "sessionid", "value": "s1", "domain": ".tiktok.com", "expirationDate": session_exp},
            {"name": "ttwid", "value": "w1", "domain": ".tiktok.com", "expirationDate": time.time() + 5 * DAY},
        ]
    )


def test_session_expiry_read_from_json_import():
    from src.infrastructure.browser.cookie_injector import BrowserCookieInjector

    exp = time.time() + 30 * DAY
    assert BrowserCookieInjector.session_expiry(_json_cookies(exp)) == pytest.approx(exp)
    assert BrowserCookieInjector.session_expiry("sessionid=abc; ttwid=x") is None


def test_injection_keeps_real_expiry_and_skips_expired(tmp_path):
    from src.infrastructure.browser.cookie_injector import BrowserCookieInjector

    exp = time.time() + 30 * DAY
    raw = json.dumps(
        [
            {"name": "sessionid", "value": "s1", "domain": ".tiktok.com", "expirationDate": exp},
            {"name": "dead", "value": "d", "domain": ".tiktok.com", "expirationDate": time.time() - 60},
        ]
    )
    assert BrowserCookieInjector.inject_to_chromium_sqlite(tmp_path / "p", raw)
    rows = dict(
        sqlite3.connect(tmp_path / "p" / "Default" / "Network" / "Cookies")
        .execute("SELECT name, expires_utc FROM cookies")
        .fetchall()
    )
    assert "dead" not in rows
    unix = (rows["sessionid"] - 11644473600000000) / 1_000_000
    assert unix == pytest.approx(exp, abs=2)


def test_repo_records_session_expiry_of_imported_json(repo):
    exp = time.time() + 30 * DAY
    pid = repo.create({"name": "A", "uuid": "uuid-cap-0005", "cookies_json": _json_cookies(exp)})
    assert repo.get_by_id(pid)["session_expires_at"] == pytest.approx(exp)


# ------------------------------------------------------------------ 4. expiry in the table
@pytest.mark.parametrize(
    ("expires_in_days", "text", "warn"),
    [(40, "Còn 40 ngày", False), (3, "Còn 3 ngày", True), (-1, "Hết hạn", True)],
)
def test_cookie_column_shows_session_expiry(qtbot, expires_in_days, text, warn):
    from src.presentation.widgets.profile_table_widget import ProfileTableWidget

    table = ProfileTableWidget()
    qtbot.addWidget(table)
    exp = time.time() + expires_in_days * DAY + 3600
    table.load_profiles([{"id": 1, "name": "A", "uuid": "u", "cookies_browser": "sessionid=x", "session_expires_at": exp}])
    item = table.item(0, 13)
    assert item.text() == text
    assert (item.foreground().color().name().lower() in ("#c42b1c", "#ca5010")) is warn
    assert "sessionid" not in item.text()  # cookie values are never shown in the table


def test_cookie_column_without_expiry_info(qtbot):
    from src.presentation.widgets.profile_table_widget import ProfileTableWidget

    table = ProfileTableWidget()
    qtbot.addWidget(table)
    table.load_profiles([{"id": 1, "name": "A", "uuid": "u", "cookies_json": "sessionid=x"}, {"id": 2, "name": "B", "uuid": "v"}])
    assert table.item(0, 13).text() == "Có cookie" and table.item(1, 13).text() == ""


# ------------------------------------------------------------------ 5. refresh session action
def _refresh(profile, launcher, capture_result=None, running_addr=None):
    from PyQt6.QtWidgets import QApplication
    from src.application.services.cookie_session_service import CaptureResult
    from src.application.workers.session_refresh_worker import SessionRefreshWorker

    QApplication.instance() or QApplication([])
    profile_repo, proxy_repo = MagicMock(), MagicMock()
    profile_repo.get_by_id.return_value = profile
    proxy_repo.get_by_id.return_value = None
    launcher._active_sdk_sessions = {profile["id"]: running_addr} if running_addr else {}
    session_service = MagicMock()
    session_service.capture.return_value = capture_result or CaptureResult(True, True, NOW + 50 * DAY, "ok")
    worker = SessionRefreshWorker(
        [profile["id"]], profile_repo, proxy_repo, launcher, session_service, page_wait_s=0, open_url=MagicMock()
    )
    results = []
    worker.signals.done.connect(lambda r: results.extend(r))
    worker.run()
    return session_service, worker, results


def test_refresh_launches_through_proxy_gate_captures_and_closes():
    profile = {"id": 3, "name": "R", "uuid": "u3", "direct_connection": 1}
    launcher = MagicMock()
    launcher.launch_via_gologin_sdk.return_value = "127.0.0.1:9333"
    session_service, worker, results = _refresh(profile, launcher)
    worker._open_url.assert_called_once_with("127.0.0.1:9333", "https://www.tiktok.com/")
    session_service.capture.assert_called_once_with(3, "127.0.0.1:9333")
    launcher.close_profile.assert_called_once()
    assert results[0]["ok"] and results[0]["profile_id"] == 3


def test_refresh_never_bypasses_the_proxy_gate():
    profile = {"id": 4, "name": "NoProxy", "uuid": "u4"}  # no proxy, no direct opt-in
    launcher = MagicMock()
    session_service, _, results = _refresh(profile, launcher)
    launcher.launch_via_gologin_sdk.assert_not_called()
    session_service.capture.assert_not_called()
    assert not results[0]["ok"]


def test_refresh_of_running_profile_captures_without_closing():
    profile = {"id": 5, "name": "Open", "uuid": "u5", "direct_connection": 1}
    launcher = MagicMock()
    session_service, _, results = _refresh(profile, launcher, running_addr="127.0.0.1:9444")
    launcher.launch_via_gologin_sdk.assert_not_called()
    session_service.capture.assert_called_once_with(5, "127.0.0.1:9444")
    launcher.close_profile.assert_not_called()
    assert results[0]["ok"]


# ------------------------------------------------------------------ window wiring
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
    win.session_capture_timer.stop()
    return win


def test_window_periodically_captures_open_sdk_sessions(qtbot, tmp_path):
    win = _window(tmp_path)
    qtbot.addWidget(win)
    win.orbita_launcher._active_sdk_sessions = {7: "127.0.0.1:9555", "uuid-7": "127.0.0.1:9555"}
    with patch("src.presentation.views.main_window.run_task") as run_task:
        win._capture_open_sessions()
    assert run_task.call_count == 1
    assert run_task.call_args.args[1:] == (7, "127.0.0.1:9555")


def _run_inline(fn, *args, on_result=None, **kwargs):
    value = fn(*args, **kwargs)
    if on_result is not None:
        on_result(value)


def test_closing_a_profile_captures_its_session_first(qtbot, tmp_path):
    win = _window(tmp_path)
    qtbot.addWidget(win)
    pid = win.profile_repo.create({"name": "C", "uuid": "uuid-close-1"})
    order = []
    win.orbita_launcher._active_sdk_sessions = {pid: "127.0.0.1:9666"}
    win.cookie_session_service = MagicMock()
    win.cookie_session_service.capture.side_effect = lambda *a: order.append("capture")
    win.orbita_launcher.close_profile = MagicMock(side_effect=lambda *a: order.append("close"))
    with patch.object(win, "_run_bg", side_effect=_run_inline):
        win._on_close_orbita([pid])
    assert order == ["capture", "close"]


def test_context_menu_has_refresh_session_action(qtbot, tmp_path):
    win = _window(tmp_path)
    qtbot.addWidget(win)
    assert hasattr(win.profile_table, "refresh_session_requested")
    with (
        patch("src.presentation.views.main_window.SessionRefreshWorker") as worker_cls,
        patch.object(win.thread_pool, "dispatch") as dispatch,
    ):
        win._on_refresh_sessions([1, 2])
    dispatch.assert_called_once_with(worker_cls.return_value)
    assert worker_cls.call_args.args[0] == [1, 2]
