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
