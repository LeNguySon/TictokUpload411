"""
Unit tests for concurrent multi-threaded video upload progress tracking and per-video logs.
Verifies signal emissions, worker step reporting, VideoUploadLogWidget filtering, and table updates.
"""

from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication
from src.application.signals.app_signals import AppSignalBus


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_signal_bus_has_upload_log_and_stage_signals():
    bus = AppSignalBus()
    assert hasattr(bus, "upload_log"), "AppSignalBus must have upload_log signal"
    assert hasattr(bus, "upload_stage_changed"), "AppSignalBus must have upload_stage_changed signal"

    # Verify signal emission and reception
    received_logs = []
    received_stages = []

    def on_log(vid, ts, stage, msg, level):
        received_logs.append((vid, ts, stage, msg, level))

    def on_stage(vid, stage):
        received_stages.append((vid, stage))

    bus.upload_log.connect(on_log)
    bus.upload_stage_changed.connect(on_stage)

    bus.upload_log.emit(101, "10:00:00", "INIT", "Khởi tạo tiến trình", "INFO")
    bus.upload_stage_changed.emit(101, "Khởi tạo...")

    assert len(received_logs) == 1
    assert received_logs[0] == (101, "10:00:00", "INIT", "Khởi tạo tiến trình", "INFO")
    assert len(received_stages) == 1
    assert received_stages[0] == (101, "Khởi tạo...")


def test_video_upload_log_widget_storage_and_filtering(qapp):
    from src.presentation.widgets.video_upload_log_widget import VideoUploadLogWidget

    widget = VideoUploadLogWidget()
    assert widget is not None

    # Simulate log events for two concurrent videos
    widget.append_log(101, "10:00:01", "INIT", "Bắt đầu tải Video 101", "INFO")
    widget.append_log(102, "10:00:02", "INIT", "Bắt đầu tải Video 102", "INFO")
    widget.append_log(101, "10:00:03", "CHUNK", "Gửi chunk 1/3 (33%)", "INFO")
    widget.append_log(102, "10:00:04", "CHUNK", "Gửi chunk 1/2 (50%)", "INFO")
    widget.append_log(101, "10:00:05", "SUCCESS", "Đăng thành công video 101", "SUCCESS")

    # Check internal buffer
    logs_101 = widget.get_logs_for_video(101)
    logs_102 = widget.get_logs_for_video(102)
    all_logs = widget.get_all_logs()

    assert len(logs_101) == 3
    assert len(logs_102) == 2
    assert len(all_logs) == 5

    # Filter to video 101
    widget.filter_by_video(101)
    displayed_text = widget.get_displayed_plain_text()
    assert "Video 101" in displayed_text
    assert "Video 102" not in displayed_text

    # Filter to video 102
    widget.filter_by_video(102)
    displayed_text = widget.get_displayed_plain_text()
    assert "Video 102" in displayed_text
    assert "Video 101" not in displayed_text

    # Filter to all
    widget.filter_by_video(None)  # None means All
    displayed_text = widget.get_displayed_plain_text()
    assert "Video 101" in displayed_text
    assert "Video 102" in displayed_text


def test_video_upload_log_widget_agentshield_redaction(qapp):
    from src.presentation.widgets.video_upload_log_widget import VideoUploadLogWidget

    widget = VideoUploadLogWidget()
    raw_message = "Payload sent with sessionid=9f8a7b6c5d4e3f2a1b0c and token act.abcdef1234567890"
    widget.append_log(105, "10:00:00", "UPLOAD", raw_message, "INFO")

    displayed_text = widget.get_displayed_plain_text()
    # Sensitive tokens should be redacted / masked
    assert "9f8a7b6c5d4e3f2a1b0c" not in displayed_text
    assert "act.abcdef1234567890" not in displayed_text
    assert "[REDACTED]" in displayed_text or "***" in displayed_text


def test_video_queue_table_widget_update_stage_and_progress(qapp):
    from src.presentation.widgets.video_queue_table_widget import VideoQueueTableWidget

    table = VideoQueueTableWidget()
    test_videos = [
        {"id": 201, "file_name": "Video_Test_1.mp4", "status": "available", "duration": 15.0},
        {"id": 202, "file_name": "Video_Test_2.mp4", "status": "available", "duration": 20.0},
    ]
    table.load_videos(test_videos)

    # Update progress and stage for video 201
    table.update_progress(201, 45.0)
    table.update_stage(201, "Đang gửi chunk (45%)")

    # Column 9 is 'Tình trạng'
    status_item = table.item(0, 9)
    assert status_item is not None
    assert "45%" in status_item.text()

    # Verify context menu action / signal
    assert hasattr(table, "view_upload_logs_requested")


def test_upload_worker_emits_step_logs_and_stages():
    from src.application.workers.upload_worker import UploadWorker

    bus = AppSignalBus()
    upload_service = MagicMock()
    upload_service.execute_upload.return_value = MagicMock(success=True, publish_id="tiktok_v123", error=None)

    emitted_logs = []
    emitted_stages = []

    bus.upload_log.connect(lambda *args: emitted_logs.append(args))
    bus.upload_stage_changed.connect(lambda *args: emitted_stages.append(args))

    worker = UploadWorker(
        video_id=301,
        profile_id=42,
        upload_service=upload_service,
        signal_bus=bus,
    )

    worker.execute()

    # Must have emitted logs and stage changes
    assert len(emitted_logs) >= 2, f"Expected at least 2 logs, got: {emitted_logs}"
    assert len(emitted_stages) >= 2, f"Expected at least 2 stage transitions, got: {emitted_stages}"

    # First log should be starting
    first_vid, _, first_stage, first_msg, _ = emitted_logs[0]
    assert first_vid == 301
    assert "START" in first_stage or "INIT" in first_stage

    # Last stage should indicate completion
    assert any(
        s[0] == 301 and ("Hoàn tất" in s[1] or "Thành công" in s[1] or "Xuất bản" in s[1]) for s in emitted_stages
    )


def test_concurrent_multi_video_upload_flow(qapp):
    """Verifies that multiple concurrent uploads are accurately segregated by video_id."""
    from src.presentation.widgets.video_queue_table_widget import VideoQueueTableWidget
    from src.presentation.widgets.video_upload_log_widget import VideoUploadLogWidget

    log_widget = VideoUploadLogWidget()
    table_widget = VideoQueueTableWidget()

    videos = [
        {"id": 401, "file_name": "Multi_Test_1.mp4", "status": "available"},
        {"id": 402, "file_name": "Multi_Test_2.mp4", "status": "available"},
        {"id": 403, "file_name": "Multi_Test_3.mp4", "status": "available"},
    ]
    table_widget.load_videos(videos)

    # Video 401: Full successful pipeline
    log_widget.append_log(401, "11:00:01", "START", "Bắt đầu video 401", "INFO")
    table_widget.update_stage(401, "Khởi tạo...")
    log_widget.append_log(401, "11:00:02", "RESERVE", "Đã khóa draft video 401", "INFO")
    log_widget.append_log(401, "11:00:03", "CHUNK", "Gửi dữ liệu (50%)", "INFO")
    table_widget.update_progress(401, 50.0)
    log_widget.append_log(401, "11:00:04", "SUCCESS", "Đăng thành công ID: tk_401", "SUCCESS")
    table_widget.update_stage(401, "Hoàn tất")
    table_widget.update_progress(401, 100.0)

    # Video 402: Fails midway
    log_widget.append_log(402, "11:00:02", "START", "Bắt đầu video 402", "INFO")
    table_widget.update_stage(402, "Khởi tạo...")
    log_widget.append_log(402, "11:00:03", "CHUNK", "Gửi dữ liệu (30%)", "INFO")
    table_widget.update_progress(402, 30.0)
    log_widget.append_log(402, "11:00:05", "ERROR", "Timeout kết nối máy chủ TikTok", "ERROR")
    table_widget.update_stage(402, "Thất bại")

    # Video 403: In progress
    log_widget.append_log(403, "11:00:04", "START", "Bắt đầu video 403", "INFO")
    log_widget.append_log(403, "11:00:05", "CHUNK", "Đang tải (60%)", "INFO")
    table_widget.update_progress(403, 60.0)

    # Verify per-video isolation
    v401_logs = log_widget.get_logs_for_video(401)
    v402_logs = log_widget.get_logs_for_video(402)
    v403_logs = log_widget.get_logs_for_video(403)

    assert len(v401_logs) == 4
    assert len(v402_logs) == 3
    assert len(v403_logs) == 2

    # Check table status items
    item_401 = table_widget.item(0, 9)
    item_402 = table_widget.item(1, 9)
    item_403 = table_widget.item(2, 9)

    assert item_401 is not None and "Hoàn tất" in item_401.text()
    assert item_402 is not None and "Thất bại" in item_402.text()
    assert item_403 is not None and "60%" in item_403.text()


def test_main_window_has_upload_log_widget_and_toggle(qapp):
    from unittest.mock import patch

    from src.presentation.views.main_window import TikTokManagerMainWindow

    with patch.object(TikTokManagerMainWindow, "refresh_all_data"):
        win = TikTokManagerMainWindow()
        # Verify console drawer is removed and video_table takes full container
        assert not hasattr(win, "upload_log_widget")
        assert not hasattr(win, "btn_toggle_upload_log")
        assert hasattr(win, "video_table")
