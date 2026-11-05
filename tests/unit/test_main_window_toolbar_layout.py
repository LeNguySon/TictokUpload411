"""Top toolbar: the profile search box has a compact width (it used to stretch across the whole window)
and the settings button stays pinned to the right edge."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication


def test_profile_search_is_compact_and_settings_stays_right(qtbot, tmp_path: Path):
    from src.infrastructure.database.migrations.runner import run_all_migrations

    db = tmp_path / "tb.db"
    run_all_migrations(db)
    with (
        patch("src.presentation.views.main_window.MetricsSyncWorker"),
        patch("src.presentation.views.main_window.SamMonnyDaemonSupervisor"),
    ):
        from src.presentation.views.main_window import PROFILE_SEARCH_WIDTH, TikTokManagerMainWindow

        win = TikTokManagerMainWindow(db_path=db)
    win.scheduler_timer.stop()
    win.profile_status_timer.stop()
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.resize(1366, 850)
    win.show()
    QApplication.processEvents()

    assert win.search_profile.width() == PROFILE_SEARCH_WIDTH <= 360
    gear_right = win.btn_settings.mapTo(win, win.btn_settings.rect().topRight()).x()
    assert gear_right >= win.width() - 40, "settings button must stay at the right edge"
    win.close()
    win.deleteLater()
