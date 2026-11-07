"""
ProxyManagerDialog read the whole proxy table on the GUI thread when opened, imported pasted proxy lists on
the GUI thread, and re-read + re-rendered everything once PER checked proxy (500 checks = 500 reloads).
"""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.application.workers.task_worker import drain_ui_tasks, process_events_until
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository


def _dialog(qtbot, tmp_path: Path, n: int = 3):
    from src.presentation.dialogs.proxy_dialog import ProxyManagerDialog

    db = tmp_path / "px.db"
    run_all_migrations(db)
    repo = ProxyRepository(db)
    for i in range(n):
        repo.create(host=f"10.0.0.{i + 1}", port=8000 + i)
    dlg = ProxyManagerDialog(proxy_repo=repo, proxy_service=MagicMock())
    qtbot.addWidget(dlg)
    return dlg, repo


def _spy_list_all(repo: ProxyRepository):
    threads: list[str] = []
    real = repo.list_all

    def spy(*a, **k):
        threads.append(threading.current_thread().name)
        return real(*a, **k)

    return threads, patch.object(repo, "list_all", side_effect=spy)


def test_proxy_list_loads_off_gui_thread(qtbot, tmp_path: Path) -> None:
    dlg, repo = _dialog(qtbot, tmp_path)
    assert drain_ui_tasks()
    threads, spy = _spy_list_all(repo)
    with spy:
        dlg.refresh_proxies()
        assert drain_ui_tasks()
    assert threads and threading.main_thread().name not in threads
    assert dlg.table.rowCount() == 3


def test_pasted_proxy_import_runs_off_gui_thread(qtbot, tmp_path: Path) -> None:
    dlg, repo = _dialog(qtbot, tmp_path, n=0)
    assert drain_ui_tasks()
    threads: list[str] = []
    real = repo.bulk_import

    def spy(lines):
        threads.append(threading.current_thread().name)
        return real(lines)

    dlg.txt_import.setPlainText("1.2.3.4:8080\n5.6.7.8:9090:user:pass")
    with patch.object(repo, "bulk_import", side_effect=spy):
        dlg._on_import()
        assert drain_ui_tasks()
    assert threads and threading.main_thread().name not in threads
    assert len(repo.list_all()) == 2
    assert process_events_until(lambda: dlg.table.rowCount() == 2)


def test_proxy_check_results_are_coalesced_into_few_reloads(qtbot, tmp_path: Path) -> None:
    dlg, repo = _dialog(qtbot, tmp_path)
    assert drain_ui_tasks(timeout_s=15)  # start from an idle UI pool (other tests may leave tasks behind)
    threads, spy = _spy_list_all(repo)
    with spy:
        for pid in range(1, 51):
            dlg._on_proxy_checked(pid, True, 120.0, "alive")
        assert process_events_until(lambda: bool(threads), timeout_s=15)
        assert drain_ui_tasks()
    assert 1 <= len(threads) <= 2  # 50 check results -> one (or two) table reloads, not 50
