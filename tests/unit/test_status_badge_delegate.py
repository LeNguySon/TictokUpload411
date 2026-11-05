"""Unit tests for StatusBadgeDelegate matching Gloglin2609 specifications.
Validates:
1. StatusBadgeDelegate theme configurations for all 8 standard MMO statuses.
2. Badge label mapping (stopped/ready -> 'Sẵn sàng', running -> 'Đang mở', etc.).
3. Delegate sizeHint has minimum width 125px and height >= 30px.
4. Delegate paint execution on QPainter for both Light and Dark palettes without errors.
5. ProfileTableWidget registers StatusBadgeDelegate on Column 12 with width >= 125px.
6. Immediate status updates during launch ('launching') and close ('ready'/'LIVE').
"""

from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QModelIndex, QRect, QSize, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPalette
from PyQt6.QtWidgets import QApplication, QStyle, QStyleOptionViewItem
from src.application.workers.task_worker import drain_ui_tasks
from src.presentation.delegates.status_badge_delegate import (
    STATUS_THEMES,
    StatusBadgeDelegate,
    get_status_config,
)
from src.presentation.widgets.profile_table_widget import ProfileTableWidget


@pytest.fixture
def app_instance():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


def test_status_themes_complete_and_accurate():
    """Verifies that all standard lifecycle statuses have valid theme tuples and labels."""
    expected_statuses = [
        "stopped",
        "ready",
        "launching",
        "running",
        "live",
        "die",
        "checkpoint",
        "error",
    ]
    for st in expected_statuses:
        assert st in STATUS_THEMES
        theme = STATUS_THEMES[st]
        # (bg_light, border_light, text_light, dot_light, bg_dark, border_dark, text_dark, dot_dark, label)
        assert len(theme) == 9
        assert isinstance(theme[8], str)
        assert len(theme[8]) > 0

    assert STATUS_THEMES["stopped"][8] == "Sẵn sàng"
    assert STATUS_THEMES["ready"][8] == "Sẵn sàng"
    assert STATUS_THEMES["running"][8] == "Đang mở"
    assert "Đang mở" in STATUS_THEMES["launching"][8]
    assert STATUS_THEMES["live"][8] == "LIVE"
    assert STATUS_THEMES["die"][8] == "DIE"
    assert STATUS_THEMES["checkpoint"][8] == "CHECKPOINT"
    assert STATUS_THEMES["error"][8] == "Lỗi"


def test_get_status_config_fallbacks():
    """Verifies that unknown or casing variations gracefully resolve to a valid theme."""
    cfg_upper = get_status_config("RUNNING", is_light=True)
    assert cfg_upper[4] == "Đang mở"

    cfg_live = get_status_config("LIVE", is_light=True)
    assert cfg_live[4] == "LIVE"

    cfg_unknown = get_status_config("something_weird", is_light=True)
    assert cfg_unknown[4] == "Sẵn sàng"


def test_status_badge_delegate_size_hint(app_instance):
    """Verifies that sizeHint enforces width >= 125px to prevent truncation."""
    delegate = StatusBadgeDelegate()
    hint = delegate.sizeHint(QStyleOptionViewItem(), QModelIndex())
    assert isinstance(hint, QSize)
    assert hint.width() >= 125
    assert hint.height() >= 30


def test_status_badge_delegate_paint_rendering(app_instance):
    """Verifies that paint renders cleanly onto a QImage without throwing exceptions."""
    delegate = StatusBadgeDelegate()
    image = QImage(200, 50, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)

    opt = QStyleOptionViewItem()
    opt.rect = QRect(0, 0, 150, 40)
    opt.state = QStyle.StateFlag.State_Enabled

    # 1. Test Light Mode
    palette_light = QPalette()
    palette_light.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
    opt.palette = palette_light

    mock_index = MagicMock()
    mock_index.data.side_effect = lambda role: (
        "running" if role in (Qt.ItemDataRole.UserRole, Qt.ItemDataRole.DisplayRole) else None
    )

    delegate.paint(painter, opt, mock_index)

    # 2. Test Dark Mode
    palette_dark = QPalette()
    palette_dark.setColor(QPalette.ColorRole.Base, QColor("#202020"))
    opt.palette = palette_dark

    mock_index.data.side_effect = lambda role: (
        "stopped" if role in (Qt.ItemDataRole.UserRole, Qt.ItemDataRole.DisplayRole) else None
    )
    delegate.paint(painter, opt, mock_index)

    painter.end()


def test_profile_table_widget_has_status_delegate_and_no_elision(app_instance):
    """Verifies that ProfileTableWidget attaches StatusBadgeDelegate to Column 12."""
    table = ProfileTableWidget()
    assert table.columnWidth(12) >= 125

    delegate = table.itemDelegateForColumn(12)
    assert isinstance(delegate, StatusBadgeDelegate)

    profiles = [
        {"id": 1, "name": "Prof1", "status": "running"},
        {"id": 2, "name": "Prof2", "status": "stopped"},
        {"id": 3, "name": "Prof3", "status": "LIVE"},
        {"id": 4, "name": "Prof4", "status": "launching"},
    ]
    table.load_profiles(profiles)

    # Check UserRole persistence for delegate rendering
    for row, p in enumerate(profiles):
        item = table.item(row, 12)
        assert item is not None
        assert item.data(Qt.ItemDataRole.UserRole) == p["status"]


def test_main_window_launch_transition_sets_launching(tmp_path, app_instance):
    """Verifies that launching Orbita transitions row status to 'launching' immediately."""
    from src.infrastructure.database.migrations.runner import run_all_migrations
    from src.infrastructure.database.repositories.profile_repository import ProfileRepository
    from src.presentation.views.main_window import TikTokManagerMainWindow

    db_file = tmp_path / "launch_test.db"
    run_all_migrations(db_file)
    prof_repo = ProfileRepository(db_file)
    p_id = prof_repo.create({"name": "TestProfile_Launch", "status": "stopped"})

    with (
        patch("src.presentation.views.main_window.setTheme"),
        patch("src.presentation.views.main_window.MetricsSyncWorker"),
    ):
        win = TikTokManagerMainWindow(db_path=db_file)
        row = win._find_profile_row_by_id(p_id)
        assert row >= 0

        # Before launch: status is stopped (Sẵn sàng)
        assert win.profile_table.item(row, 12).data(Qt.ItemDataRole.UserRole) == "stopped"

        # Simulate starting signal
        win._on_orbita_profile_starting(p_id, "TestProfile_Launch")
        assert win.profile_table.item(row, 12).data(Qt.ItemDataRole.UserRole) == "launching"

        # Simulate launched signal
        win._on_orbita_profile_launched(p_id, "TestProfile_Launch", "9222")
        assert win.profile_table.item(row, 12).data(Qt.ItemDataRole.UserRole) == "running"

        # Simulate closing
        with patch.object(win.orbita_launcher, "close_profile", return_value=True):
            win._on_close_orbita([p_id])
            drain_ui_tasks()  # loads/actions run on the UI pool since UI responsiveness P1
        assert win.profile_table.item(row, 12).data(Qt.ItemDataRole.UserRole) == "stopped"

        win.scheduler_timer.stop()
        if hasattr(win, "profile_status_timer"):
            win.profile_status_timer.stop()
        win.profile_table.clearSelection()
        win.close()
        win.deleteLater()
        app_instance.processEvents()
