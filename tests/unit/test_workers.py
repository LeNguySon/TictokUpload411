"""
Unit tests for Qt Concurrency Workers: UploadWorker, ProxyCheckWorker, ThreadPoolManager.
Strict TDD - Phase 2 (RED)
"""

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QCoreApplication
from sammonny import ProxyHealthResult, RemoteStatus, UploadResult
from src.application.signals.app_signals import AppSignalBus
from src.application.workers.proxy_check_worker import ProxyCheckWorker
from src.application.workers.thread_pool_manager import ThreadPoolManager
from src.application.workers.upload_worker import UploadWorker


@pytest.fixture(scope="session")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


def test_upload_worker_execution_and_signals(qapp):
    mock_upload_service = MagicMock()
    mock_upload_service.execute_upload.return_value = UploadResult(
        success=True,
        draft_id="draft_abc",
        publish_id="v_pub_tiktok_888",
        status=RemoteStatus.PROCESSING_UPLOAD,
        bytes_uploaded=1024,
        total_bytes=1024,
    )

    signal_bus = AppSignalBus.instance()
    completed_events = []
    signal_bus.upload_completed.connect(lambda v_id, pub_id: completed_events.append((v_id, pub_id)))

    worker = UploadWorker(
        video_id=101,
        profile_id=202,
        upload_service=mock_upload_service,
        signal_bus=signal_bus,
    )

    # Run synchronously
    worker.run()

    assert len(completed_events) == 1
    assert completed_events[0] == (101, "v_pub_tiktok_888")
    mock_upload_service.execute_upload.assert_called_once()


def test_proxy_check_worker_batch(qapp):
    mock_proxy_service = MagicMock()
    mock_proxy_service.check_proxy.side_effect = [
        ProxyHealthResult(is_alive=True, latency_ms=45.0, egress_ip="1.2.3.4", country="US"),
        ProxyHealthResult(is_alive=False, latency_ms=-1.0, error="Critical IP Leak"),
    ]

    signal_bus = AppSignalBus.instance()
    checked_events = []
    signal_bus.proxy_checked.connect(lambda p_id, alive, lat, err: checked_events.append((p_id, alive, lat, err)))

    worker = ProxyCheckWorker(
        proxy_ids=[1, 2],
        proxy_service=mock_proxy_service,
        signal_bus=signal_bus,
    )

    worker.run()

    assert len(checked_events) == 2
    assert checked_events[0][1] is True  # Alive
    assert checked_events[1][1] is False  # Dead


def test_thread_pool_manager_dispatch_and_cancel(qapp):
    pool_mgr = ThreadPoolManager.instance()
    assert pool_mgr is not None
    assert pool_mgr.max_thread_count >= 1

    mock_worker = MagicMock()
    mock_worker.is_cancelled = False

    pool_mgr.track_worker(mock_worker)
    pool_mgr.cancel_all()
    assert mock_worker.cancel.called
