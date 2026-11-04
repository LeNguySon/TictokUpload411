"""
Integration test for TikTokManagerMainWindow and Fluent UI Dual-Table layout.
"""

import tempfile
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.presentation.views.main_window import TikTokManagerMainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_main_window_creation_and_layout(qapp):
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "gui_integration.db"
        run_all_migrations(db_path)

        window = TikTokManagerMainWindow(db_path=db_path)
        assert window is not None
        assert "SSMATool" in window.windowTitle()

        # Check top table (Profiles)
        assert window.profile_table.columnCount() == 29
        assert window.profile_table.horizontalHeaderItem(0).text() == "STT"
        assert window.profile_table.horizontalHeaderItem(1).text() == "Avt"
        assert window.profile_table.horizontalHeaderItem(2).text() == "Tên hồ sơ"
        assert window.profile_table.horizontalHeaderItem(12).text() == "Tình trạng"

        # Check bottom table (Videos)
        assert window.video_table.columnCount() == 14
        assert window.video_table.horizontalHeaderItem(0).text() == "STT"
        assert window.video_table.horizontalHeaderItem(1).text() == "Tiêu đề"
        assert window.video_table.horizontalHeaderItem(9).text() == "Source"

        # Check default project dropdown has item
        assert window.project_combo.count() >= 1

        # Check Settings Menu is created and has actions
        assert window.settings_menu is not None
        actions = window.settings_menu.actions()
        assert len(actions) >= 10

        # Check searching video filters rows
        window.search_video.setText("non_existent_search_query")
        # Video table rows should be hidden
        for r in range(window.video_table.rowCount()):
            assert window.video_table.isRowHidden(r)
        window.search_video.clear()

        # Check searching profile filters rows
        window.search_profile.setText("ghost_profile")
        for r in range(window.profile_table.rowCount()):
            assert window.profile_table.isRowHidden(r)
        window.search_profile.clear()

        window.close()
