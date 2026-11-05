"""
Unit tests verifying the hierarchical context menu tree structure and unified dialog design standards.
Part of ECC Development Lifecycle - Strict TDD (RED -> GREEN -> REFACTOR).
"""

import pytest
from PyQt6.QtGui import QContextMenuEvent
from PyQt6.QtWidgets import QApplication, QPushButton, QWidget
from qfluentwidgets import Action, FluentIcon, PrimaryPushButton, PushButton, RoundMenu
from src.presentation.widgets.profile_table_widget import ProfileTableWidget
from src.presentation.widgets.video_queue_table_widget import VideoQueueTableWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def get_all_menu_actions_recursive(menu: RoundMenu) -> list[Action]:
    """Recursively collect all actions and submenu actions from RoundMenu."""
    res = list(menu.actions())
    for sub in getattr(menu, "_subMenus", []):
        if isinstance(sub, RoundMenu):
            res.extend(get_all_menu_actions_recursive(sub))
    return res


def test_profile_table_hierarchical_context_menu_structure(qapp, monkeypatch):
    """
    Verifies that ProfileTableWidget context menu has been restructured into
    an industrial, hierarchical tree with <= 10 root items and 5 dedicated submenus.
    """
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
        }
    ]
    widget.load_profiles(mock_profiles)
    widget.selectRow(0)

    rect = widget.visualRect(widget.model().index(0, 0))
    click_pos = rect.center()
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, click_pos, widget.mapToGlobal(click_pos))

    captured_root_actions: list[Action] = []
    captured_menu: RoundMenu | None = None

    def mock_menu_exec(menu_self, *args, **kwargs):
        nonlocal captured_root_actions, captured_menu
        captured_menu = menu_self
        captured_root_actions = menu_self.actions()
        return None

    monkeypatch.setattr("qfluentwidgets.RoundMenu.exec", mock_menu_exec)
    widget.contextMenuEvent(event)

    assert captured_menu is not None
    # Root non-separator items must be concise (at most 10 items instead of 22)
    root_non_sep = [act for act in captured_root_actions if not act.isSeparator()]
    assert len(root_non_sep) <= 10, f"Root menu too bloated: {len(root_non_sep)} items"

    root_texts = [act.text() for act in root_non_sep]
    assert any("Mở Trình Duyệt" in t for t in root_texts)
    assert any("Đóng Trình Duyệt" in t for t in root_texts)
    assert any("Nạp Video" in t for t in root_texts)
    assert any("Thùng Rác" in t for t in root_texts)

    # Submenus check via getattr(captured_menu, '_subMenus', [])
    submenus = getattr(captured_menu, "_subMenus", [])
    submenu_titles = [sub.title() for sub in submenus]

    assert any("Sức Khỏe" in t or "Kênh TikTok" in t for t in submenu_titles), "Missing Sức Khỏe & Kênh TikTok submenu"
    assert any("Proxy" in t for t in submenu_titles), "Missing Proxy submenu"
    assert any("Quản Lý Hồ Sơ" in t for t in submenu_titles), "Missing Quản Lý Hồ Sơ submenu"
    assert any("Sao Chép" in t for t in submenu_titles), "Missing Sao Chép Thông Tin submenu"
    assert any("Trạng Thái" in t for t in submenu_titles), "Missing Đổi Trạng Thái submenu"

    # Verify all nested actions are present across submenus
    all_actions = get_all_menu_actions_recursive(captured_menu)
    all_texts = [act.text() for act in all_actions]

    assert any("Kiểm Tra Cookie" in t for t in all_texts)
    assert any("Đồng Bộ Số Liệu" in t for t in all_texts)
    assert any("Gậy Vi Phạm" in t for t in all_texts)
    assert any("Radar" in t for t in all_texts)
    assert any("Avatar, Bio, Tên" in t for t in all_texts)
    assert any("Xoay IP Proxy" in t for t in all_texts)
    assert any("Ping / Live Proxy" in t for t in all_texts)
    assert any("Chuyển Vào Dự Án" in t for t in all_texts)
    assert any("Mở Thư Mục Hồ Sơ" in t for t in all_texts)

    # Ensure no emoji prefix in action text (vector icons used instead)
    for act in all_actions:
        # Text should not start with emoji shield or clipboard
        text = act.text().strip()
        assert not text.startswith("🛡️"), f"Action '{text}' should use vector FluentIcon instead of emoji"
        assert not text.startswith("📋"), f"Action '{text}' should use vector FluentIcon instead of emoji"


def test_dialog_helpers_create_dialog_header(qapp):
    """Verifies dialog_helpers.create_dialog_header creates a standardized banner."""
    from src.presentation.dialogs.dialog_helpers import create_dialog_header

    parent = QWidget()
    header_widget = create_dialog_header(
        icon=FluentIcon.EDIT,
        title="Tiêu Đề Thử Nghiệm",
        subtitle="Mô tả hướng dẫn người dùng thử nghiệm",
        parent=parent,
    )
    assert header_widget is not None
    assert header_widget.layout() is not None


def test_account_health_dialog_has_zero_raw_qpushbutton(qapp):
    """Verifies AccountHealthDialog uses Fluent buttons instead of raw QPushButton."""
    from src.presentation.dialogs.account_health_dialog import AccountHealthDialog

    dialog = AccountHealthDialog(profile_id=1)
    # Must not contain any QPushButtons that are not Fluent PushButtons
    for btn in dialog.findChildren(QPushButton):
        assert isinstance(btn, (PushButton, PrimaryPushButton)), f"Raw QPushButton found: {btn}"


def test_all_dialogs_use_fluent_headers_and_margins():
    """Verifies that all 20 application dialogs (incl. license activation) follow the unified design standard."""
    import glob
    from pathlib import Path

    dialog_files = glob.glob("src/presentation/dialogs/*.py")
    dialog_modules = [f for f in dialog_files if not f.endswith("__init__.py") and not f.endswith("dialog_helpers.py")]
    assert len(dialog_modules) == 20, f"Expected 20 dialog modules, found {len(dialog_modules)}"

    for file_path in dialog_modules:
        content = Path(file_path).read_text(encoding="utf-8")
        base = Path(file_path).name
        assert "create_dialog_header" in content, f"{base} missing create_dialog_header"
        assert "setContentsMargins" in content, f"{base} missing setContentsMargins"
        assert "FluentIcon" in content, f"{base} missing FluentIcon"
        assert "QPushButton\b" not in content, f"{base} should not import raw QPushButton"


def test_video_queue_table_context_menu_crisp_icons(qapp, monkeypatch):
    """Verifies VideoQueueTableWidget context menu has sharp vector icons and proper structure."""
    widget = VideoQueueTableWidget()
    mock_videos = [
        {
            "id": 201,
            "file_name": "dance_trend.mp4",
            "file_path": "C:/videos/dance_trend.mp4",
            "tiktok_video_id": "789123456",
            "status": "available",
        }
    ]
    widget.load_videos(mock_videos)
    widget.selectRow(0)

    rect = widget.visualRect(widget.model().index(0, 0))
    click_pos = rect.center()
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, click_pos, widget.mapToGlobal(click_pos))

    captured_menu: RoundMenu | None = None

    def mock_menu_exec(menu_self, *args, **kwargs):
        nonlocal captured_menu
        captured_menu = menu_self
        return None

    monkeypatch.setattr("qfluentwidgets.RoundMenu.exec", mock_menu_exec)
    widget.contextMenuEvent(event)

    assert captured_menu is not None
    all_actions = get_all_menu_actions_recursive(captured_menu)
    assert len(all_actions) >= 5
    for act in all_actions:
        assert act.icon() is not None, f"Action {act.text()} missing icon"
