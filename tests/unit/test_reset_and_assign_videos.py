import pytest
from PyQt6.QtCore import Qt
from src.infrastructure.database.repositories.video_repository import VideoRepository
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.presentation.widgets.video_queue_table_widget import VideoQueueTableWidget

def test_video_queue_table_widget_has_reset_and_assign_signals(qtbot):
    widget = VideoQueueTableWidget()
    qtbot.addWidget(widget)
    
    assert hasattr(widget, "reset_status_requested")
    assert hasattr(widget, "assign_profile_requested")

def test_video_queue_table_display_log_text(qtbot):
    widget = VideoQueueTableWidget()
    qtbot.addWidget(widget)
    
    videos = [
        {"id": 1, "title": "Vid 1", "status": "failed", "error_message": None},
        {"id": 2, "title": "Vid 2", "status": "failed", "error_message": "Invalid params"},
        {"id": 3, "title": "Vid 3", "status": "available", "error_message": None},
    ]
    widget.load_videos(videos)
    
    # Row 0: failed with no error_message should show readable text, not bare '-'
    item0 = widget.item(0, 11)
    assert item0 is not None
    assert "-" not in item0.text() or "Thất bại" in item0.text()
    
    # Row 1: failed with error_message
    item1 = widget.item(1, 11)
    assert item1 is not None
    assert "Invalid params" in item1.text()
    
    # Row 2: available
    item2 = widget.item(2, 11)
    assert item2 is not None
    assert "Sẵn sàng" in item2.text() or "-" in item2.text()
