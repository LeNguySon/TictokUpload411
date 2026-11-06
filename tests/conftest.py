"""
Pytest configuration and global fixtures for TikTok MMO Desktop application.
Enforces thread safety, memory hygiene, and singleton isolation across test suites.
"""

import pytest


@pytest.fixture(autouse=True)
def cleanup_qt_singletons():
    """Resets global Qt singletons before and after each test to prevent cross-suite contamination."""
    from src.application.signals.app_signals import AppSignalBus
    from src.application.workers.thread_pool_manager import ThreadPoolManager

    ThreadPoolManager.reset_instance()
    AppSignalBus.reset_instance()
    yield
    ThreadPoolManager.reset_instance()
    AppSignalBus.reset_instance()


@pytest.fixture(autouse=True)
def never_kill_real_browsers(monkeypatch):
    """Safety net: tests must never scan-and-kill real Chrome/Orbita processes on the dev machine.

    BrowserProcessSupervisor.cleanup_orphan_browsers() with no explicit orphan list scans the real OS
    (when psutil is installed) and terminates every chrome/orbita whose command line mentions
    "profiles". Tests that trigger "Dọn dẹp trình duyệt" would otherwise kill the developer's own
    browsers. Explicit orphan lists, or a mocked psutil module, still run the real logic.
    """
    from src.infrastructure.browser import process_supervisor as ps

    try:
        import psutil as real_psutil
    except ImportError:
        return

    original = ps.BrowserProcessSupervisor.cleanup_orphan_browsers

    def guarded(self, orphans=None, profiles_dir=None):
        if orphans is None and ps.psutil is real_psutil:
            return []
        return original(self, orphans=orphans, profiles_dir=profiles_dir)

    monkeypatch.setattr(ps.BrowserProcessSupervisor, "cleanup_orphan_browsers", guarded)


@pytest.fixture(autouse=True)
def test_license(monkeypatch, tmp_path):
    """Every test runs with a full (Gói 3) license and a temp license file: tests never read or write the
    developer's real %APPDATA%\\TAVM\\license.dat. Tests about plans/locking set their own entitlements."""
    import time

    from src.domain.licensing import entitlements
    from src.domain.licensing.claims import LicenseClaims

    monkeypatch.setenv("TAVM_LICENSE_FILE", str(tmp_path / "license.dat"))
    now = int(time.time())
    entitlements.set_current(
        LicenseClaims.from_dict(
            {"lid": "test", "sub": "Test", "plan": "pro", "iat": now - 60, "exp": now + 365 * 86400,
             "mid": "0000-0000-0000-0000"},
            kid="test",
        )
    )
    yield
    entitlements.set_current(None)


@pytest.fixture(autouse=True)
def no_public_ip_lookup(monkeypatch):
    """The leak policy looks up the machine's public IP over the network: never from tests."""
    monkeypatch.setattr("src.domain.policies.network_leak_policy.discover_public_ip", lambda timeout=5.0: None)


@pytest.fixture(autouse=True)
def isolated_ui_settings(monkeypatch, tmp_path):
    """Tests must never read/write the developer's real UI settings (Windows registry) and must not
    run the real exit cache cleanup on whatever `profiles/` dirs exist: every test gets a temp ini
    with clean_cache_on_exit=False (tests that need it enable it explicitly)."""
    from PyQt6.QtCore import QSettings

    try:
        from src.presentation.views.main_window import TikTokManagerMainWindow
    except Exception:
        return
    ini = tmp_path / "ui_settings.ini"
    seed = QSettings(str(ini), QSettings.Format.IniFormat)
    seed.setValue("clean_cache_on_exit", False)
    seed.sync()
    monkeypatch.setattr(
        TikTokManagerMainWindow, "_settings", lambda self: QSettings(str(ini), QSettings.Format.IniFormat)
    )
