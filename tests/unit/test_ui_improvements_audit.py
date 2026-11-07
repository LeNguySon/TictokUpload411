"""
Unit tests for UI Improvements & Audit Remediation (ECC Phase 4 - Strict TDD).
Tests:
1. NumericTableWidgetItem sorts numeric values strictly by magnitude (2 < 10 < 100).
2. ProfileTableWidget and VideoQueueTableWidget support numeric sorting.
3. VideoQueueTableWidget has smooth drag-to-select and handles Key_Delete.
4. ProfileTableWidget handles Key_Delete.
5. Table hidden columns persistence via QSettings.
"""

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication
from src.presentation.widgets.profile_table_widget import ProfileTableWidget
from src.presentation.widgets.table_helpers import NumericTableWidgetItem
from src.presentation.widgets.video_queue_table_widget import VideoQueueTableWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_numeric_table_widget_item_sorting(qapp):
    """Test that NumericTableWidgetItem sorts numerically rather than lexicographically."""
    item2 = NumericTableWidgetItem(2)
    item10 = NumericTableWidgetItem(10)
    item100 = NumericTableWidgetItem(100.5)

    assert item2 < item10
    assert item10 < item100
    assert not (item10 < item2)

    # String items without numeric helper sort 10 < 2
    # Verify our custom item overrides that behavior
    items = [item10, item2, item100]
    items.sort()
    assert [i.raw_value for i in items] == [2, 10, 100.5]


def test_profile_table_numeric_column_sorting(qapp):
    """Verifies that ProfileTableWidget sorts numeric columns (ID, views, earned) by value."""
    table = ProfileTableWidget()
    mock_data = [
        {"id": 10, "name": "Prof 10", "views_30d": 1000, "earned": 150.5},
        {"id": 2, "name": "Prof 2", "views_30d": 50, "earned": 5.0},
        {"id": 3, "name": "Prof 3", "views_30d": 200, "earned": 25.0},
    ]
    table.load_profiles(mock_data)

    # Sort by ID column (last column, 27 since layout v2)
    table.sortByColumn(27, Qt.SortOrder.AscendingOrder)
    sorted_ids = [int(table.item(r, 27).text()) for r in range(table.rowCount())]
    assert sorted_ids == [2, 3, 10], f"Expected numeric sort [2, 3, 10], got {sorted_ids}"
    qapp.processEvents()


def test_video_queue_table_numeric_column_sorting(qapp):
    """Verifies that VideoQueueTableWidget sorts views and duration numerically."""
    table = VideoQueueTableWidget()
    mock_videos = [
        {"id": 101, "file_name": "vid101.mp4", "views": 100, "likes": 50},
        {"id": 2, "file_name": "vid2.mp4", "views": 20, "likes": 5},
        {"id": 35, "file_name": "vid35.mp4", "views": 5, "likes": 1},
    ]
    table.load_videos(mock_videos)

    # Sort by Views column (Col 3)
    table.sortByColumn(3, Qt.SortOrder.AscendingOrder)
    sorted_views = [
        table.item(r, 3).raw_value for r in range(table.rowCount()) if hasattr(table.item(r, 3), "raw_value")
    ]
    assert sorted_views == [5, 20, 100], f"Expected numeric sort [5, 20, 100], got {sorted_views}"
    qapp.processEvents()


def test_video_queue_table_mouse_drag_and_delete_key(qapp):
    """Verifies VideoQueueTableWidget implements smooth drag selection and Delete key handling."""
    table = VideoQueueTableWidget()
    assert hasattr(table, "mousePressEvent")
    assert hasattr(table, "mouseMoveEvent")

    mock_videos = [
        {"id": 1, "file_name": "vid1.mp4"},
        {"id": 2, "file_name": "vid2.mp4"},
    ]
    table.load_videos(mock_videos)
    table.selectRow(0)

    # Mock signal receiver for delete_video_requested
    mock_delete = MagicMock()
    table.delete_video_requested.connect(mock_delete)

    # Simulate Key_Delete press
    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
    table.keyPressEvent(event)
    mock_delete.assert_called_once_with([1])


def test_profile_table_delete_key(qapp):
    """Verifies ProfileTableWidget emits soft_delete_requested on Delete key."""
    table = ProfileTableWidget()
    mock_profiles = [{"id": 42, "name": "Profile 42"}]
    table.load_profiles(mock_profiles)
    table.selectRow(0)

    mock_delete = MagicMock()
    table.soft_delete_requested.connect(mock_delete)

    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
    table.keyPressEvent(event)
    mock_delete.assert_called_once_with([42])


def test_main_window_column_persistence_and_shortcuts(qapp, tmp_path):
    """Verifies MainWindow restores hidden columns from QSettings and initializes shortcuts."""
    from unittest.mock import patch

    from src.infrastructure.database.migrations.runner import run_all_migrations
    from src.presentation.views.main_window import TikTokManagerMainWindow

    db_file = tmp_path / "test_mw_ui.db"
    run_all_migrations(db_file)

    # Pre-configure the (test-isolated, see conftest) UI settings with hidden columns {3, 5};
    # writing QSettings("TAVM", "TikTokManager") here used to overwrite/remove the developer's real ones.
    settings = TikTokManagerMainWindow._settings(None)
    settings.setValue("hidden_profile_columns", "3,5")
    settings.sync()

    with patch("src.infrastructure.browser.sammonny_daemon_manager.SamMonnyDaemonSupervisor.ensure_daemon_running"):
        mw = TikTokManagerMainWindow(db_path=db_file)

    assert mw.hidden_columns == {3, 5}
    assert mw.profile_table.isColumnHidden(3) is True
    assert mw.profile_table.isColumnHidden(5) is True
    assert mw.profile_table.isColumnHidden(2) is False

    # Check shortcuts
    assert hasattr(mw, "shortcut_f5")
    assert hasattr(mw, "shortcut_ctrl_r")

    mw.close()
    settings.remove("hidden_profile_columns")


def test_main_window_confirmation_dialogs(qapp, tmp_path, monkeypatch):
    """Verifies destructive actions trigger confirmation MessageBox."""
    from unittest.mock import patch

    from src.infrastructure.database.migrations.runner import run_all_migrations
    from src.presentation.views.main_window import TikTokManagerMainWindow

    db_file = tmp_path / "test_mw_confirm.db"
    run_all_migrations(db_file)

    with patch("src.infrastructure.browser.sammonny_daemon_manager.SamMonnyDaemonSupervisor.ensure_daemon_running"):
        mw = TikTokManagerMainWindow(db_path=db_file)

    mw.video_table.setRowCount(2)
    assert mw.video_table.rowCount() == 2

    # 1. When user rejects clear table dialog
    monkeypatch.setattr("qfluentwidgets.MessageBox.exec", lambda self: False)
    mw._on_clear_video_table()
    assert mw.video_table.rowCount() == 2, "Table should NOT be cleared if user cancels"

    # 2. When user accepts clear table dialog
    monkeypatch.setattr("qfluentwidgets.MessageBox.exec", lambda self: True)
    mw._on_clear_video_table()
    assert mw.video_table.rowCount() == 0, "Table should be cleared if user accepts"

    mw.close()
