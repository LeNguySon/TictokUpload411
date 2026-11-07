"""
Bulk profile import ran its whole loop on the GUI thread: per row a SamMonny daemon call (profile create), a
Chromium cookie-DB write and several SQLite writes, so importing 100 accounts froze the app for minutes.
The loop now runs on the UI pool (import_profiles), reports progress and can be cancelled.
"""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from src.application.workers.task_worker import drain_ui_tasks, process_events_until
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository


@pytest.fixture
def repos(tmp_path: Path):
    db = tmp_path / "bulk.db"
    run_all_migrations(db)
    return ProfileRepository(db_path=db), ProjectRepository(db_path=db), ProxyRepository(db_path=db), tmp_path


def _rows(n: int) -> list[dict]:
    return [{"user": f"acc_{i}", "pass": "pw_fake", "cookie": f"sessionid=fake_{i}"} for i in range(n)]


def _offline(tmp_path: Path):
    """No real daemon: profile creation fails fast -> local fallback in tmp."""
    return (
        patch(
            "src.application.services.gologin_sync_service.GoLoginSyncService.create_real_gologin_profile",
            side_effect=RuntimeError("daemon offline (test)"),
        ),
        patch(
            "src.infrastructure.browser.orbita_launcher.OrbitaLauncher.resolve_profile_dir",
            side_effect=lambda p: tmp_path / "profiles" / str(p.get("uuid") or p.get("name")),
        ),
        patch("src.infrastructure.browser.cookie_injector.BrowserCookieInjector.seed_profile_cookies"),
    )


def test_import_profiles_creates_rows_reports_progress_and_counts(repos) -> None:
    from src.presentation.dialogs.bulk_add_profile_dialog import import_profiles

    profile_repo, project_repo, proxy_repo, tmp = repos
    progress: list[tuple[int, int]] = []
    a, b, c = _offline(tmp)
    with a, b, c:
        summary = import_profiles(
            _rows(3),
            profile_repo=profile_repo,
            project_repo=project_repo,
            proxy_repo=proxy_repo,
            project_id=None,
            auto_inject=True,
            progress=lambda done, total: progress.append((done, total)),
        )
    assert summary.created == 3 and summary.injected == 3 and not summary.cancelled
    assert progress == [(1, 3), (2, 3), (3, 3)]
    assert sorted(p["name"] for p in profile_repo.list_all()) == ["acc_0", "acc_1", "acc_2"]


def test_import_profiles_stops_when_cancelled(repos) -> None:
    from src.presentation.dialogs.bulk_add_profile_dialog import import_profiles

    profile_repo, project_repo, proxy_repo, tmp = repos
    done_rows: list[int] = []
    a, b, c = _offline(tmp)
    with a, b, c:
        summary = import_profiles(
            _rows(5),
            profile_repo=profile_repo,
            project_repo=project_repo,
            proxy_repo=proxy_repo,
            project_id=None,
            auto_inject=False,
            progress=lambda done, total: done_rows.append(done),
            cancelled=lambda: len(done_rows) >= 2,
        )
    assert summary.cancelled and summary.created == 2
    assert len(profile_repo.list_all()) == 2


def test_dialog_import_runs_off_gui_thread_and_keeps_ui_responsive(qtbot, repos) -> None:
    from src.presentation.dialogs import bulk_add_profile_dialog as mod

    profile_repo, project_repo, proxy_repo, tmp = repos
    dlg = mod.BulkAddProfileDialog(profile_repo=profile_repo, project_repo=project_repo, proxy_repo=proxy_repo)
    qtbot.addWidget(dlg)
    threads: list[str] = []
    release = threading.Event()

    def slow_create(**kwargs):
        threads.append(threading.current_thread().name)
        release.wait(5)
        raise RuntimeError("daemon offline (test)")

    a, b, c = _offline(tmp)
    with (
        a, b, c,
        patch(
            "src.application.services.gologin_sync_service.GoLoginSyncService.create_real_gologin_profile",
            side_effect=slow_create,
        ),
        patch.object(dlg, "_get_parsed_rows", return_value=_rows(2)),
        patch.object(mod, "InfoBar") as info,
    ):
        dlg._on_import_all()
        # The GUI thread returned immediately: the import is still running in the background.
        assert process_events_until(lambda: bool(threads), timeout_s=5)
        assert not dlg.btn_import.isEnabled()
        release.set()
        assert drain_ui_tasks(timeout_s=10)

    assert threading.main_thread().name not in threads
    assert len(profile_repo.list_all()) == 2
    assert "Đã tạo 2 hồ sơ" in info.success.call_args.kwargs["content"]
    assert dlg.result() == dlg.DialogCode.Accepted


def test_closing_dialog_cancels_running_import(qtbot, repos) -> None:
    from src.presentation.dialogs import bulk_add_profile_dialog as mod

    profile_repo, project_repo, proxy_repo, tmp = repos
    dlg = mod.BulkAddProfileDialog(profile_repo=profile_repo, project_repo=project_repo, proxy_repo=proxy_repo)
    qtbot.addWidget(dlg)
    started = threading.Event()
    release = threading.Event()

    def slow_create(**kwargs):
        started.set()
        release.wait(5)
        raise RuntimeError("daemon offline (test)")

    a, b, c = _offline(tmp)
    with (
        a, b, c,
        patch(
            "src.application.services.gologin_sync_service.GoLoginSyncService.create_real_gologin_profile",
            side_effect=slow_create,
        ),
        patch.object(dlg, "_get_parsed_rows", return_value=_rows(4)),
        patch.object(mod, "InfoBar", MagicMock()),
    ):
        dlg._on_import_all()
        assert started.wait(5)
        dlg.reject()  # user closes the dialog mid-import
        release.set()
        assert drain_ui_tasks(timeout_s=10)

    assert len(profile_repo.list_all()) == 1  # the row in flight finishes, the rest is not imported


def test_import_result_after_dialog_destroyed_does_not_crash(qapp, repos) -> None:
    """The app may close (dialog deleted) while the import thread still runs: late progress/result must be
    dropped, not delivered to a dead dialog (access violation)."""
    from src.presentation.dialogs import bulk_add_profile_dialog as mod

    profile_repo, project_repo, proxy_repo, tmp = repos
    dlg = mod.BulkAddProfileDialog(profile_repo=profile_repo, project_repo=project_repo, proxy_repo=proxy_repo)
    started = threading.Event()
    release = threading.Event()

    def slow_create(**kwargs):
        started.set()
        release.wait(5)
        raise RuntimeError("daemon offline (test)")

    a, b, c = _offline(tmp)
    with (
        a, b, c,
        patch(
            "src.application.services.gologin_sync_service.GoLoginSyncService.create_real_gologin_profile",
            side_effect=slow_create,
        ),
        patch.object(dlg, "_get_parsed_rows", return_value=_rows(1)),
        patch.object(mod, "InfoBar", MagicMock()),
    ):
        dlg._on_import_all()
        assert started.wait(5)
        dlg.deleteLater()
        qapp.sendPostedEvents(None, 0)  # DeferredDelete: the C++ dialog is gone
        qapp.processEvents()
        del dlg
        release.set()
        assert drain_ui_tasks(timeout_s=10)

    assert len(profile_repo.list_all()) == 1  # the import itself still completed
