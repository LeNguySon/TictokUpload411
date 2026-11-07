"""Backup export/import (zip + many SQLite writes) ran on the GUI thread; it now runs on the UI pool."""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import patch

from src.application.workers.task_worker import drain_ui_tasks
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository


def _repos(db: Path):
    run_all_migrations(db)
    return ProjectRepository(db), ProfileRepository(db), ProxyRepository(db)


def test_export_then_import_run_off_gui_thread(qtbot, tmp_path: Path) -> None:
    from src.presentation.dialogs import sync_transfer_dialog as mod

    src_proj, src_prof, src_px = _repos(tmp_path / "src.db")
    src_prof.create({"name": "acc_export", "status": "stopped"})
    zip_path = tmp_path / "backup.zip"

    threads: list[str] = []
    real_export, real_import = mod.export_project_dataset, mod.import_project_dataset

    def spy_export(**kw):
        threads.append(threading.current_thread().name)
        return real_export(**kw)

    def spy_import(**kw):
        threads.append(threading.current_thread().name)
        return real_import(**kw)

    dlg = mod.SyncTransferDialog(src_proj, src_prof, src_px)
    qtbot.addWidget(dlg)
    dlg.txt_export_path.setText(str(zip_path))
    with patch.object(mod, "export_project_dataset", side_effect=spy_export), patch.object(mod, "InfoBar") as info:
        dlg._on_start_export()
        assert not dlg.btn_start_export.isEnabled()
        assert drain_ui_tasks()
    assert zip_path.exists() and info.success.called and dlg.btn_start_export.isEnabled()

    dst_proj, dst_prof, dst_px = _repos(tmp_path / "dst.db")
    dlg2 = mod.SyncTransferDialog(dst_proj, dst_prof, dst_px)
    qtbot.addWidget(dlg2)
    dlg2.txt_import_path.setText(str(zip_path))
    with patch.object(mod, "import_project_dataset", side_effect=spy_import), patch.object(mod, "InfoBar") as info2:
        dlg2._on_start_import()
        assert not dlg2.btn_start_import.isEnabled()
        assert drain_ui_tasks()
    assert [p["name"] for p in dst_prof.list_all()] == ["acc_export"] and info2.success.called

    assert len(threads) == 2 and threading.main_thread().name not in threads
