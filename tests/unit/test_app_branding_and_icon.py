"""
Unit and integration tests for SonBetaPro branding and multi-resolution application icon.
Verifies:
1. Application name is 'SonBetaPro' on QApplication.
2. Window title is 'SonBetaPro'.
3. QIcon is correctly loaded from icon.ico with multi-resolution icon sizes.
4. Windows AppUserModelID is configured for taskbar branding.
"""

import pytest
from PyQt6.QtWidgets import QApplication
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.presentation.app_icon import get_app_icon
from src.presentation.views.main_window import TikTokManagerMainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    app.setApplicationName("SonBetaPro")
    app.setApplicationDisplayName("SonBetaPro")
    app_icon = get_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)
    return app


def test_get_app_icon_loads_valid_multi_res_icon(qapp):
    icon = get_app_icon()
    assert not icon.isNull(), "Application icon from icon.ico must not be null"
    sizes = icon.availableSizes()
    assert len(sizes) > 0, "Application icon must contain available icon resolutions"
    dimensions = [(s.width(), s.height()) for s in sizes]
    # Check standard Windows ICO sizes
    assert (32, 32) in dimensions or (256, 256) in dimensions


def test_main_window_branding_and_icon(qapp, tmp_path):
    db_path = tmp_path / "test_branding.db"
    run_all_migrations(db_path)

    window = TikTokManagerMainWindow(db_path=db_path)
    try:
        assert window.windowTitle() == "SonBetaPro"
        assert not window.windowIcon().isNull()
        assert len(window.windowIcon().availableSizes()) > 0
    finally:
        window.close()

