"""Unit tests for the collapsible / expandable video table panel in TikTokManagerMainWindow."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication
from src.infrastructure.database.migrations.runner import run_all_migrations


def _create_test_window(tmp_path: Path):
    db = tmp_path / "test_collapse.db"
    run_all_migrations(db)
    with (
        patch("src.presentation.views.main_window.MetricsSyncWorker"),
        patch("src.presentation.views.main_window.SamMonnyDaemonSupervisor"),
    ):
        from src.presentation.views.main_window import TikTokManagerMainWindow

        win = TikTokManagerMainWindow(db_path=db)
    win.scheduler_timer.stop()
    win.profile_status_timer.stop()
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.resize(1280, 800)
    win.show()
    QApplication.processEvents()
    return win


def test_initial_state_is_expanded(qapp, tmp_path: Path):
    win = _create_test_window(tmp_path)
    try:
        assert hasattr(win, "btn_toggle_video")
        assert win._is_video_collapsed is False
        assert win.video_table.isVisible() is True
        assert "Thu gọn" in win.btn_toggle_video.toolTip()
    finally:
        win.close()
        win.deleteLater()


def test_collapse_and_expand_toggle(qapp, tmp_path: Path):
    win = _create_test_window(tmp_path)
    try:
        # 1. Collapse
        win._toggle_video_panel_collapse()
        QApplication.processEvents()
        assert win._is_video_collapsed is True
        assert win.video_table.isVisible() is False
        assert "Hiển thị lại" in win.btn_toggle_video.toolTip()

        # 2. Expand
        win._toggle_video_panel_collapse()
        QApplication.processEvents()
        assert win._is_video_collapsed is False
        assert win.video_table.isVisible() is True
        assert "Thu gọn" in win.btn_toggle_video.toolTip()
    finally:
        win.close()
        win.deleteLater()


def test_header_click_triggers_toggle(qapp, tmp_path: Path):
    win = _create_test_window(tmp_path)
    try:
        assert win._is_video_collapsed is False

        # Click label
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(10.0, 10.0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        win.lbl_video_header.mousePressEvent(event)
        QApplication.processEvents()
        assert win._is_video_collapsed is True

        # Click again to restore
        win.lbl_video_header.mousePressEvent(event)
        QApplication.processEvents()
        assert win._is_video_collapsed is False
    finally:
        win.close()
        win.deleteLater()


def test_splitter_size_restoration(qapp, tmp_path: Path):
    win = _create_test_window(tmp_path)
    try:
        win.splitter.setSizes([450, 350])
        QApplication.processEvents()

        # Collapse
        win._collapse_video_panel()
        QApplication.processEvents()
        sizes_collapsed = win.splitter.sizes()
        assert sizes_collapsed[1] < 80  # Shrunk to toolbar dock

        # Expand
        win._expand_video_panel()
        QApplication.processEvents()
        sizes_expanded = win.splitter.sizes()
        assert sizes_expanded[1] >= 200  # Restored to previous height
    finally:
        win.close()
        win.deleteLater()


def test_auto_expand_when_adding_videos(qapp, tmp_path: Path):
    win = _create_test_window(tmp_path)
    try:
        # Collapse first
        win._collapse_video_panel()
        assert win._is_video_collapsed is True

        # Calling _expand_video_panel directly or through hooks restores it
        win._expand_video_panel()
        assert win._is_video_collapsed is False
        assert win.video_table.isVisible() is True
    finally:
        win.close()
        win.deleteLater()


def test_ctrl_b_shortcut_registered(qapp, tmp_path: Path):
    win = _create_test_window(tmp_path)
    try:
        assert hasattr(win, "shortcut_ctrl_b")
        assert win.shortcut_ctrl_b.key().toString() == "Ctrl+B"
    finally:
        win.close()
        win.deleteLater()
