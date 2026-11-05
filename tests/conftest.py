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
