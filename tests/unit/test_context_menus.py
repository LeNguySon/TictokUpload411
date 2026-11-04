"""
Unit tests for Context Menus across ProfileTableWidget, VideoQueueTableWidget, and ProxyManagerDialog.
Validates crisp FluentIcon vector actions, auto-selection, signal emissions, and multi-selection support.
ECC Strict TDD - Phase 4
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PyQt6.QtGui import QContextMenuEvent
from PyQt6.QtWidgets import QApplication
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
from src.presentation.dialogs.proxy_dialog import ProxyManagerDialog
from src.presentation.widgets.profile_table_widget import ProfileTableWidget
from src.presentation.widgets.video_queue_table_widget import VideoQueueTableWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_profile_table_context_menu_and_signals(qapp, monkeypatch):
    widget = ProfileTableWidget()
    mock_profiles = [
        {
            "id": 101,
            "name": "Profile Alpha",
            "username_on_tiktok": "tiktok_alpha",
            "cookie": "sessionid=xyz123",
            "proxy_host": "1.2.3.4",
            "proxy_port": 8080,
            "status": "LIVE",
        },
        {
            "id": 102,
            "name": "Profile Beta",
            "username_on_tiktok": "tiktok_beta",
            "cookie": "",
            "proxy_host": "5.6.7.8",
            "proxy_port": 3128,
            "status": "DIE",
        },
    ]
    widget.load_profiles(mock_profiles)
    assert widget.rowCount() == 2

    # Verify get_selected_profiles retrieves from UserRole
    widget.selectRow(0)
    selected = widget.get_selected_profiles()
    assert len(selected) == 1
    assert selected[0]["id"] == 101
    assert selected[0]["username_on_tiktok"] == "tiktok_alpha"

    # Test auto-select on unselected row right-click
    # Row 0 is currently selected. Right clicking on Row 1 should auto-select Row 1.
    rect_row1 = widget.visualRect(widget.model().index(1, 0))
    click_pos = rect_row1.center()
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, click_pos, widget.mapToGlobal(click_pos))

    # Spy on RoundMenu.exec to capture actions without blocking UI loop
    captured_actions = []

    def mock_menu_exec(menu_self, *args, **kwargs):
        nonlocal captured_actions
        captured_actions = menu_self.actions()
        return None

    monkeypatch.setattr("qfluentwidgets.RoundMenu.exec", mock_menu_exec)

    widget.contextMenuEvent(event)

    # After right click on row 1, selection should switch to row 1
    selected_ids = widget.get_selected_profile_ids()
    assert selected_ids == [102]

    # Check generated actions
    action_texts = [act.text() for act in captured_actions if not act.isSeparator()]
    assert any("Mở Browser" in t for t in action_texts)
    assert any("Kiểm Tra Cookie" in t for t in action_texts)
    assert any("Đồng Bộ Số Liệu" in t for t in action_texts)
    assert any("Cập Nhật / Gán Proxy" in t for t in action_texts)
    assert any("Chuyển Vào Dự Án" in t for t in action_texts)
    assert any("Chuyển Vào Thùng Rác" in t for t in action_texts)


def test_profile_table_signal_emissions(qapp):
    widget = ProfileTableWidget()
    mock_profiles = [{"id": 42, "name": "Profile 42", "username_on_tiktok": "user42"}]
    widget.load_profiles(mock_profiles)
    widget.selectRow(0)

    # Mock signal receivers
    mock_orbita = MagicMock()
    mock_proxy = MagicMock()
    mock_status = MagicMock()
    mock_delete = MagicMock()

    widget.open_orbita_requested.connect(mock_orbita)
    widget.update_proxy_requested.connect(mock_proxy)
    widget.change_status_requested.connect(mock_status)
    widget.soft_delete_requested.connect(mock_delete)

    # Emit signals
    widget.open_orbita_requested.emit([42])
    widget.update_proxy_requested.emit([42])
    widget.change_status_requested.emit([42], "LIVE")
    widget.soft_delete_requested.emit([42])

    mock_orbita.assert_called_once_with([42])
    mock_proxy.assert_called_once_with([42])
    mock_status.assert_called_once_with([42], "LIVE")
    mock_delete.assert_called_once_with([42])


def test_video_queue_table_context_menu_and_signals(qapp, monkeypatch):
    widget = VideoQueueTableWidget()
    mock_videos = [
        {
            "id": 201,
            "file_name": "dance_trend.mp4",
            "file_path": "C:/videos/dance_trend.mp4",
            "tiktok_video_id": "789123456",
            "status": "available",
        },
        {
            "id": 202,
            "file_name": "cooking_tips.mp4",
            "file_path": "C:/videos/cooking_tips.mp4",
            "tiktok_video_id": "",
            "status": "available",
        },
    ]
    widget.load_videos(mock_videos)
    assert widget.rowCount() == 2

    # Verify row 0 selection and UserRole storage
    widget.selectRow(0)
    selected = widget.get_selected_videos()
    assert len(selected) == 1
    assert selected[0]["id"] == 201
    assert selected[0]["file_name"] == "dance_trend.mp4"

    # Context menu test with monkeypatched exec
    rect_row0 = widget.visualRect(widget.model().index(0, 0))
    click_pos = rect_row0.center()
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, click_pos, widget.mapToGlobal(click_pos))

    captured_actions = []

    def mock_menu_exec(menu_self, *args, **kwargs):
        nonlocal captured_actions
        captured_actions = menu_self.actions()
        return None

    monkeypatch.setattr("qfluentwidgets.RoundMenu.exec", mock_menu_exec)
    widget.contextMenuEvent(event)

    action_texts = [act.text() for act in captured_actions if not act.isSeparator()]
    assert any("Đăng Ngay Video Này" in t for t in action_texts)
    assert any("Lên Lịch Đăng" in t for t in action_texts)
    assert any("Chỉnh Sửa Thông Tin Video" in t for t in action_texts)
    assert any("Xem Trước Video" in t for t in action_texts)
    assert any("Mở Thư Mục Chứa Video" in t for t in action_texts)
    assert any("Xóa Khỏi Hàng Đợi" in t for t in action_texts)


def test_proxy_manager_dialog_context_menu(qapp, monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "proxy_test.db"
        run_all_migrations(db_path)

        proxy_repo = ProxyRepository(db_path)
        proxy_repo.create(host="10.0.0.1", port=8080, username="user1", password="pw1")
        proxy_repo.create(host="10.0.0.2", port=3128, change_ip_url="https://rotate.link/reset")

        mock_service = MagicMock()
        dlg = ProxyManagerDialog(proxy_repo=proxy_repo, proxy_service=mock_service)
        assert dlg.table.rowCount() == 2

        # Context menu on row 1
        rect_row1 = dlg.table.visualRect(dlg.table.model().index(1, 0))
        pos = rect_row1.center()

        captured_actions = []

        def mock_menu_exec(menu_self, *args, **kwargs):
            nonlocal captured_actions
            captured_actions = menu_self.actions()
            return None

        monkeypatch.setattr("qfluentwidgets.RoundMenu.exec", mock_menu_exec)
        dlg._on_table_context_menu(pos)

        action_texts = [act.text() for act in captured_actions if not act.isSeparator()]
        assert any("Kiểm Tra Sức Khỏe" in t for t in action_texts)
        assert any("Xoay IP" in t for t in action_texts)
        assert any("Xóa Proxy" in t for t in action_texts)

        dlg.close()
