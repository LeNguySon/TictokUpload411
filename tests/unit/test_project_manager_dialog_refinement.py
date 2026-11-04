"""
Unit tests for ProjectManagerDialog Refinement:
1. Video folder removed from ProjectManagerDialog (kho video removed).
2. Direct inline cell editing disabled (NoEditTriggers).
3. Dedicated Edit Project Name button and functionality.
Strict TDD - Phase RED -> GREEN -> REFACTOR.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QAbstractItemView, QApplication
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.presentation.dialogs.project_dialog import ProjectManagerDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    db_file = tmp_path / "project_dialog_refinement_test.db"
    run_all_migrations(db_file)
    return db_file


def test_project_manager_dialog_removes_video_folder_and_disables_cell_editing(qapp, test_db: Path):
    """Verifies kho video input and column are removed, and cell editing is blocked."""
    repo = ProjectRepository(test_db)
    dlg = ProjectManagerDialog(repo)

    # 1. Kho video input is removed from dialog form
    assert not hasattr(dlg, "folder_input")

    # 2. Table columns are 6 and do not contain 'Thư Mục Video'
    assert dlg.table.columnCount() == 6
    headers = [dlg.table.horizontalHeaderItem(i).text() for i in range(dlg.table.columnCount())]
    assert "Thư Mục Video" not in headers
    assert headers == ["ID", "Tên Dự Án", "Tổng Profiles", "Số Acc LIVE", "Tổng Lượt View", "Tổng $ Earned"]

    # 3. Direct cell clicking cannot edit cell content
    assert dlg.table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers

    # 4. Item flags do not include ItemIsEditable
    if dlg.table.rowCount() > 0:
        item = dlg.table.item(0, 1)
        assert item is not None
        from PyQt6.QtCore import Qt

        assert not (item.flags() & Qt.ItemFlag.ItemIsEditable)


def test_project_manager_dialog_edit_project_name_action(qapp, test_db: Path):
    """Verifies user can edit project name via dedicated edit action."""
    repo = ProjectRepository(test_db)
    p_id = repo.create(name="Dự Án Cũ")

    dlg = ProjectManagerDialog(repo)
    assert hasattr(dlg, "btn_edit")

    # Select row with p_id
    target_row = -1
    for r in range(dlg.table.rowCount()):
        item = dlg.table.item(r, 0)
        if item and item.text() == str(p_id):
            target_row = r
            break
    assert target_row != -1

    dlg.table.selectRow(target_row)

    # Mock user entering new name in QInputDialog
    with patch("PyQt6.QtWidgets.QInputDialog.getText", return_value=("Dự Án Đã Sửa", True)):
        dlg._on_edit_project_name()

    # Verify repository updated
    updated = repo.get_by_id(p_id)
    assert updated is not None
    assert updated["name"] == "Dự Án Đã Sửa"

    # Verify table refreshed
    name_item = dlg.table.item(target_row, 1)
    assert name_item is not None
    assert name_item.text() == "Dự Án Đã Sửa"
