"""
Unit tests for Video Queue Table Drag & Drop and Queue Auto-Advance.
Strict TDD - Phase 2
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QMimeData, QUrl
from PyQt6.QtWidgets import QApplication
from src.presentation.widgets.video_queue_table_widget import VideoQueueTableWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_video_queue_drag_drop_accepts_video_files(qapp, tmp_path: Path):
    table = VideoQueueTableWidget()
    assert table.acceptDrops() is True

    # Create dummy video files
    vid1 = tmp_path / "dance_challenge.mp4"
    vid1.write_bytes(b"dummy mp4 content")
    vid2 = tmp_path / "funny_cat.mov"
    vid2.write_bytes(b"dummy mov content")
    non_vid = tmp_path / "notes.txt"
    non_vid.write_bytes(b"text file")

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(vid1)), QUrl.fromLocalFile(str(vid2)), QUrl.fromLocalFile(str(non_vid))])

    # Test dragEnterEvent
    enter_event = MagicMock()
    enter_event.mimeData.return_value = mime
    table.dragEnterEvent(enter_event)
    enter_event.acceptProposedAction.assert_called_once()

    # Test dropEvent with signal capture
    dropped_files = []
    table.files_dropped.connect(lambda paths: dropped_files.extend(paths))

    drop_event = MagicMock()
    drop_event.mimeData.return_value = mime
    table.dropEvent(drop_event)
    drop_event.acceptProposedAction.assert_called_once()

    # Only vid1 and vid2 should be emitted, non_vid should be filtered out
    assert len(dropped_files) == 2
    assert str(vid1) in dropped_files
    assert str(vid2) in dropped_files
    assert str(non_vid) not in dropped_files


def test_video_queue_drag_drop_recursively_scans_folders(qapp, tmp_path: Path):
    table = VideoQueueTableWidget()

    # Create nested folder structure
    folder = tmp_path / "batch_reup"
    folder.mkdir()
    subfolder = folder / "shorts"
    subfolder.mkdir()

    vid_a = folder / "clip_a.mp4"
    vid_a.write_bytes(b"content a")
    vid_b = subfolder / "clip_b.webm"
    vid_b.write_bytes(b"content b")

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(folder))])

    dropped_files = []
    table.files_dropped.connect(lambda paths: dropped_files.extend(paths))

    drop_event = MagicMock()
    drop_event.mimeData.return_value = mime
    table.dropEvent(drop_event)

    assert len(dropped_files) == 2
    assert str(vid_a) in dropped_files
    assert str(vid_b) in dropped_files
