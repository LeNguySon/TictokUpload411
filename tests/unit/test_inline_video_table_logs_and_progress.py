"""
Unit tests for inline video table upload logs and progress tracking.
Verifies column structure, inline progress updates, real-time log appending, and error display on the table.
"""

from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QApplication
from src.presentation.widgets.table_helpers import get_video_table_headers
from src.presentation.widgets.video_queue_table_widget import VideoQueueTableWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_video_table_headers_contain_progress_and_logs():
    headers = get_video_table_headers()
    assert "Tiến trình" in headers, "Table headers must include 'Tiến trình'"
    assert "Nhật Ký Upload" in headers, "Table headers must include 'Nhật Ký Upload'"

    # Check index positions
    idx_prog = headers.index("Tiến trình")
    idx_log = headers.index("Nhật Ký Upload")
    assert idx_prog == 10
    assert idx_log == 11


def test_video_queue_table_inline_progress_and_log_updates(qapp):
    table = VideoQueueTableWidget()
    test_videos = [
        {"id": 501, "file_name": "Video_Inline_1.mp4", "status": "available"},
        {"id": 502, "file_name": "Video_Inline_2.mp4", "status": "available"},
    ]
    table.load_videos(test_videos)

    # 1. Update progress for Video 501
    table.update_progress(501, 45.0)
    pbar = table._progress_bars.get(501)
    assert pbar is not None
    assert pbar.value() == 45

    # 2. Append log for Video 501
    table.append_log(501, "12:00:01", "CHUNK", "Đang gửi chunk 2/5 (45%)", "INFO")
    row_501 = table.find_row_by_video_id(501)
    assert row_501 is not None

    log_item = table.item(row_501, 11)  # Col 11 is 'Nhật Ký Upload'
    assert log_item is not None
    assert "Đang gửi chunk" in log_item.text()
    assert "45%" in log_item.text()

    # 3. Append error for Video 502
    table.set_video_error(502, "Mất kết nối máy chủ TikTok (Timeout)")
    row_502 = table.find_row_by_video_id(502)
    assert row_502 is not None

    err_item = table.item(row_502, 11)
    assert err_item is not None
    assert "❌ Lỗi" in err_item.text()
    assert "Mất kết nối" in err_item.text()

    # Check status column (Col 9)
    status_item_502 = table.item(row_502, 9)
    assert status_item_502 is not None
    assert "Thất bại" in status_item_502.text() or "Lỗi" in status_item_502.text()


def test_main_window_has_clean_bottom_layout_without_console_widget(qapp):
    from src.presentation.views.main_window import TikTokManagerMainWindow

    with patch.object(TikTokManagerMainWindow, "refresh_all_data"):
        win = TikTokManagerMainWindow()
        # Verify console widget is removed from main window
        assert not hasattr(win, "upload_log_widget"), "upload_log_widget should be removed"
        assert not hasattr(win, "btn_toggle_upload_log"), "btn_toggle_upload_log should be removed"
        # Video table should exist directly
        assert hasattr(win, "video_table")
