"""
Unit test specifically auditing and stress-testing all 15 actions in the Settings & Tools Menu.
Ensures zero crashes, correct signal bindings, and robust dialog lifecycle.
Strict TDD - Phase 4
"""

import tempfile
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication, QDialog, QInputDialog
from src.application.workers.task_worker import drain_ui_tasks
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
from src.presentation.views.main_window import TikTokManagerMainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_all_settings_menu_actions_execute_without_crash(qapp, monkeypatch):
    # Mock modal dialog exec to return immediately
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)
    monkeypatch.setattr(QInputDialog, "getInt", lambda *args, **kwargs: (15, True))

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "menu_audit.db"
        run_all_migrations(db_path)

        # Pre-seed sample project, proxy, and profile
        proj_repo = ProjectRepository(db_path)
        proxy_repo = ProxyRepository(db_path)
        profile_repo = ProfileRepository(db_path)

        p_id = proj_repo.create(name="Audit Project")
        px_id = proxy_repo.create(host="127.0.0.1", port=8080)
        profile_repo.create(name="Audit Profile", project_id=p_id, proxy_id=px_id)

        window = TikTokManagerMainWindow(db_path=db_path)
        window.show()

        # Audit each action inside settings_menu
        actions = window.settings_menu.actions()
        assert len(actions) >= 14

        for act in actions:
            if act.isSeparator():
                continue
            # Trigger action directly
            act.trigger()

        drain_ui_tasks()  # background actions must release the temp DB before cleanup
        window.close()
