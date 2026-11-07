"""
Unit and integration tests for Profile Creation, Storage Directory Resolution,
and Chromium SQLite Cookie Auto-Injection.
Complies with ECC Development Lifecycle & AgentShield Tier-1 Security Standard.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from src.infrastructure.browser.cookie_injector import BrowserCookieInjector
from src.infrastructure.browser.orbita_launcher import OrbitaLauncher
from src.infrastructure.credentials.dpapi import protect_text


@pytest.fixture
def temp_profile_dir():
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


def test_browser_cookie_injector_creates_sqlite_schema_if_missing(temp_profile_dir: Path):
    """Verifies that injecting cookies into a fresh profile automatically creates the Chromium SQLite DB schema."""
    target_db = temp_profile_dir / "Default" / "Network" / "Cookies"
    assert not target_db.exists()

    cookie_raw = "sessionid=test_session_12345; sid_tt=test_sid_67890; my_token=abc"
    success = BrowserCookieInjector.inject_to_chromium_sqlite(temp_profile_dir, cookie_raw)

    assert success is True
    assert target_db.is_file()

    conn = sqlite3.connect(str(target_db))
    try:
        # Check meta table
        meta_rows = dict(conn.execute("SELECT key, value FROM meta;").fetchall())
        assert meta_rows.get("version") == "24"

        # Check cookies table
        cur = conn.cursor()
        rows = cur.execute("SELECT name, value, host_key, is_httponly FROM cookies ORDER BY name;").fetchall()
        cookie_dict = {r[0]: {"value": r[1], "host_key": r[2], "is_httponly": r[3]} for r in rows}

        assert "sessionid" in cookie_dict
        assert cookie_dict["sessionid"]["value"] == "test_session_12345"
        assert cookie_dict["sessionid"]["host_key"] == ".tiktok.com"
        assert cookie_dict["sessionid"]["is_httponly"] == 1

        assert "sid_tt" in cookie_dict
        assert cookie_dict["sid_tt"]["value"] == "test_sid_67890"
        assert cookie_dict["sid_tt"]["is_httponly"] == 1

        assert "my_token" in cookie_dict
        assert cookie_dict["my_token"]["value"] == "abc"
    finally:
        conn.close()


def test_browser_cookie_injector_decrypts_dpapi_envelope(temp_profile_dir: Path):
    """Verifies that DPAPI encrypted cookie envelopes are seamlessly unwrapped before SQLite insertion."""
    raw_cookies = "sessionid=secure_dpapi_session; passport_csrf_token=csrf_token_secret"
    encrypted_envelope = protect_text(raw_cookies)
    assert encrypted_envelope.startswith("gloglin:dpapi:v1:")

    success = BrowserCookieInjector.inject_to_chromium_sqlite(temp_profile_dir, encrypted_envelope)
    assert success is True

    target_db = temp_profile_dir / "Default" / "Network" / "Cookies"
    conn = sqlite3.connect(str(target_db))
    try:
        rows = conn.execute("SELECT name, value FROM cookies WHERE name = 'sessionid';").fetchall()
        assert len(rows) == 1
        assert rows[0][1] == "secure_dpapi_session"
    finally:
        conn.close()


def test_resolve_profile_dir_resolves_daemon_and_creates_if_needed(temp_profile_dir: Path):
    """Verifies profile directory resolution logic across daemon directory, absolute path, and fallback creation."""
    launcher = OrbitaLauncher()

    with patch("src.infrastructure.browser.orbita_launcher.daemon_profiles_dir", return_value=temp_profile_dir):
        # 1. Existing UUID directory in daemon profiles dir
        existing_uuid = "11111111-2222-3333-4444-555555555555"
        existing_path = temp_profile_dir / existing_uuid
        existing_path.mkdir(parents=True, exist_ok=True)

        res = launcher.resolve_profile_dir({"uuid": existing_uuid, "name": "Test1"})
        assert res == existing_path

        # 2. Existing relative path pointing to daemon uuid
        res_rel = launcher.resolve_profile_dir({"storage_dir": f"profiles/{existing_uuid}"})
        assert res_rel == existing_path

        # 3. Brand new profile that does not exist yet -> should be created in daemon dir
        new_uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        new_path = launcher.resolve_profile_dir({"uuid": new_uuid, "name": "BrandNewProfile"})
        assert new_path == temp_profile_dir / new_uuid
        assert new_path.is_dir()


def test_orbita_launcher_prepares_profile_and_injects_cookies(temp_profile_dir: Path):
    """Verifies that prepare_profile_environment auto-injects cookies if present in profile_data."""
    launcher = OrbitaLauncher()
    profile_data = {
        "uuid": "test-cookie-inject-uuid",
        "name": "AutoInjectProfile",
        "cookie": "sessionid=profile_auto_cookie_val",
    }

    resolved = launcher.prepare_profile_environment(temp_profile_dir, profile_data)
    # Compare resolved paths: Windows TEMP may be an 8.3 short path (RUNNER~1 on GitHub runners).
    assert resolved.resolve() == temp_profile_dir.resolve()

    cookies_db = temp_profile_dir / "Default" / "Network" / "Cookies"
    assert cookies_db.is_file()

    conn = sqlite3.connect(str(cookies_db))
    try:
        rows = conn.execute("SELECT name, value FROM cookies WHERE name = 'sessionid';").fetchall()
        assert len(rows) == 1
        assert rows[0][1] == "profile_auto_cookie_val"
    finally:
        conn.close()


def test_main_window_open_profile_folder_resolves_and_opens(temp_profile_dir: Path):
    """Verifies MainWindow._on_open_profile_folder resolves daemon path and triggers os.startfile."""
    from src.presentation.views.main_window import MainWindow

    dummy_win = MagicMock(spec=MainWindow)

    existing_folder = temp_profile_dir / "my_custom_profile"
    existing_folder.mkdir(parents=True, exist_ok=True)

    with patch("src.infrastructure.browser.orbita_launcher.daemon_profiles_dir", return_value=temp_profile_dir):
        with patch("os.startfile") as mock_startfile:
            MainWindow._on_open_profile_folder(dummy_win, "my_custom_profile")
            mock_startfile.assert_called_once_with(str(existing_folder))


def test_gologin_sync_service_creates_profile_and_injects_sqlite(temp_profile_dir: Path):
    """Verifies GoLoginSyncService.create_real_gologin_profile creates folder on disk and injects SQLite cookies."""
    from src.application.services.gologin_sync_service import GoLoginSyncService

    mock_profile_repo = MagicMock()
    mock_profile_repo.create.return_value = 999
    mock_project_repo = MagicMock()

    sync_svc = GoLoginSyncService(
        profile_repo=mock_profile_repo,
        project_repo=mock_project_repo,
        daemon_supervisor=MagicMock(),
    )

    test_uuid = "custom-test-uuid-9999"
    with patch("src.infrastructure.browser.orbita_launcher.daemon_profiles_dir", return_value=temp_profile_dir):
        with patch("sammonny.gologin.gologin.GoLogin") as mock_gl_cls:
            mock_gl = MagicMock()
            mock_gl.create.return_value = test_uuid
            mock_gl_cls.return_value = mock_gl

            prof_id = sync_svc.create_real_gologin_profile(
                name="AutoProfile",
                cookie="sessionid=live_login_session_999",
            )
            assert prof_id == 999

            prof_dir = temp_profile_dir / test_uuid
            assert prof_dir.is_dir()

            cookies_file = prof_dir / "Default" / "Network" / "Cookies"
            assert cookies_file.is_file()

            conn = sqlite3.connect(str(cookies_file))
            try:
                rows = conn.execute("SELECT name, value FROM cookies WHERE name = 'sessionid';").fetchall()
                assert len(rows) == 1
                assert rows[0][1] == "live_login_session_999"
            finally:
                conn.close()
