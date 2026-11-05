"""Footer checkbox "Dọn cache tất cả dự án trước khi thoát" must really clean caches on exit.

It used to only trim the RAM of the exiting process (no cache was cleaned), was never persisted
and was a raw QCheckBox.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QSettings


@pytest.fixture
def window_factory(qtbot, tmp_path: Path, monkeypatch):
    from src.infrastructure.database.migrations.runner import run_all_migrations
    from src.infrastructure.database.repositories.profile_repository import ProfileRepository

    db = tmp_path / "exit.db"
    run_all_migrations(db)
    repo = ProfileRepository(db)
    dirs = []
    for i in range(2):
        d = tmp_path / "profiles" / f"p{i}"
        d.mkdir(parents=True)
        dirs.append(d)
        repo.create({"name": f"P{i}", "uuid": f"uuid-exit-{i:04d}", "storage_dir": str(d)})
    ini = tmp_path / "settings.ini"  # never touch the user's real (registry) settings
    from src.presentation.views.main_window import TikTokManagerMainWindow

    # For the whole test (not only construction): toggling the checkbox writes settings.
    monkeypatch.setattr(
        TikTokManagerMainWindow, "_settings", lambda self: QSettings(str(ini), QSettings.Format.IniFormat)
    )

    def make():
        with (
            patch("src.presentation.views.main_window.MetricsSyncWorker"),
            patch("src.presentation.views.main_window.SamMonnyDaemonSupervisor"),
        ):
            from src.presentation.views.main_window import TikTokManagerMainWindow

            win = TikTokManagerMainWindow(db_path=db)
        win.scheduler_timer.stop()
        win.profile_status_timer.stop()
        return win

    return make, dirs, ini


def test_checkbox_is_fluent_and_persisted(window_factory):
    from qfluentwidgets import CheckBox

    make, _, ini = window_factory
    win = make()
    assert isinstance(win.chk_clean_exit, CheckBox)
    win.chk_clean_exit.setChecked(False)
    assert QSettings(str(ini), QSettings.Format.IniFormat).value("clean_cache_on_exit", type=bool) is False
    win.deleteLater()
    win2 = make()
    assert win2.chk_clean_exit.isChecked() is False
    win2.deleteLater()


def test_checked_box_cleans_profile_caches_on_exit(window_factory):
    make, dirs, _ = window_factory
    win = make()
    win.chk_clean_exit.setChecked(True)
    with patch("src.infrastructure.browser.cache_cleaner.BrowserCacheCleaner.clean_cache", return_value={}) as clean:
        win.close()
    assert clean.call_count == 1
    cleaned = {Path(p).resolve() for p in clean.call_args.args[0]}
    assert cleaned == {d.resolve() for d in dirs}
    win.deleteLater()


def test_running_profiles_are_not_cleaned(window_factory):
    make, dirs, _ = window_factory
    win = make()
    win.chk_clean_exit.setChecked(True)
    running = dirs[0].resolve()
    with (
        patch("src.infrastructure.browser.cache_cleaner.BrowserCacheCleaner.clean_cache", return_value={}) as clean,
        patch(
            "src.infrastructure.browser.process_supervisor.BrowserProcessSupervisor.is_process_running",
            side_effect=lambda d: Path(d).resolve() == running,
        ),
    ):
        win.close()
    cleaned = {Path(p).resolve() for p in clean.call_args.args[0]}
    assert running not in cleaned and dirs[1].resolve() in cleaned
    win.deleteLater()


def test_unchecked_box_cleans_nothing(window_factory):
    make, _, _ = window_factory
    win = make()
    win.chk_clean_exit.setChecked(False)
    with patch("src.infrastructure.browser.cache_cleaner.BrowserCacheCleaner.clean_cache") as clean:
        win.close()
    clean.assert_not_called()
    win.deleteLater()
