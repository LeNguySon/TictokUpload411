"""
Unit tests for AppSignalBus.
Strict TDD - Phase 2 (RED)
"""

import pytest
from PyQt6.QtCore import QCoreApplication
from src.application.signals.app_signals import AppSignalBus


@pytest.fixture(scope="session")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


def test_app_signal_bus_singleton_and_emission(qapp):
    bus1 = AppSignalBus.instance()
    bus2 = AppSignalBus.instance()
    assert bus1 is bus2

    received_progress = []

    def on_progress(video_id: int, done: int, total: int, pct: float):
        received_progress.append((video_id, done, total, pct))

    bus1.upload_progress.connect(on_progress)
    bus1.upload_progress.emit(10, 512, 1024, 50.0)

    assert len(received_progress) == 1
    assert received_progress[0] == (10, 512, 1024, 50.0)
    bus1.upload_progress.disconnect(on_progress)
