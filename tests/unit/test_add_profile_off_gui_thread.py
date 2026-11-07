"""
Creating one profile called the SamMonny daemon (profile create), seeded the Chromium cookie DB and wrote
SQLite on the GUI thread. create_profile() now runs on the UI pool; the dialog closes when it is done.
"""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.application.workers.task_worker import drain_ui_tasks, process_events_until
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository


def test_new_profile_is_created_off_gui_thread(qtbot, tmp_path: Path) -> None:
    from src.presentation.dialogs.add_profile_dialog import AddProfileDialog

    db = tmp_path / "add.db"
    run_all_migrations(db)
    profiles = ProfileRepository(db)
    dlg = AddProfileDialog(
        profile_repo=profiles, project_repo=ProjectRepository(db), proxy_repo=ProxyRepository(db), vault=MagicMock()
    )
    qtbot.addWidget(dlg)
    dlg.name_input.setText("Acc Async")
    threads: list[str] = []
    release = threading.Event()

    def slow_create(**kwargs):
        threads.append(threading.current_thread().name)
        release.wait(5)
        return profiles.create({"name": kwargs["name"], "status": "stopped"})

    with patch(
        "src.application.services.gologin_sync_service.GoLoginSyncService.create_real_gologin_profile",
        side_effect=slow_create,
    ):
        dlg._on_save()
        assert process_events_until(lambda: bool(threads), timeout_s=5)
        assert not dlg.btn_save.isEnabled()  # GUI thread is free while the daemon call runs
        release.set()
        assert drain_ui_tasks(timeout_s=10)

    assert threading.main_thread().name not in threads
    assert [p["name"] for p in profiles.list_all()] == ["Acc Async"]
    assert dlg.result() == dlg.DialogCode.Accepted
