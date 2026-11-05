"""Profile `privacy` convention: 0 = public, 1 = private (TikTok privateAccount), NULL = unknown.

The schema default (1) made every never-synced profile look private; the bulk-edit dialog wrote
strings ("PUBLIC"/"PRIVATE"/"FRIENDS" - the latter is a video setting) and the table showed raw values.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize(
    ("value", "synced", "label"),
    [
        (0, "2026-11-05 10:00:00", "Công khai"),
        (1, "2026-11-05 10:00:00", "Riêng tư"),
        ("0", "2026-11-05 10:00:00", "Công khai"),
        ("PUBLIC", None, "Công khai"),
        ("PRIVATE", None, "Riêng tư"),
        (None, None, "—"),
        (1, None, "—"),  # schema default on a never-synced profile is not a fact
    ],
)
def test_privacy_column_label(qapp, qtbot, value, synced, label):
    from src.presentation.widgets.profile_table_widget import ProfileTableWidget

    table = ProfileTableWidget()
    qtbot.addWidget(table)
    table.load_profiles([{"id": 1, "name": "P", "privacy": value, "statistic_date_update": synced}])
    assert table.item(0, 22).text() == label


def test_new_profiles_have_unknown_privacy(tmp_path: Path):
    db = tmp_path / "pv.db"
    run_all_migrations(db)
    repo = ProfileRepository(db)
    pid = repo.create({"name": "New", "uuid": "uuid-pv-0001"})
    assert repo.get_by_id(pid)["privacy"] is None


def test_bulk_edit_writes_integer_privacy(qapp, qtbot, tmp_path: Path):
    from src.infrastructure.database.repositories.project_repository import ProjectRepository
    from src.presentation.dialogs.bulk_edit_profile_dialog import BulkEditProfileDialog

    db = tmp_path / "be.db"
    run_all_migrations(db)
    repo = ProfileRepository(db)
    pid = repo.create({"name": "B", "uuid": "uuid-pv-0002"})
    dlg = BulkEditProfileDialog([pid], repo, ProjectRepository(db))
    qtbot.addWidget(dlg)
    values = [dlg.combo_privacy.itemData(i) for i in range(dlg.combo_privacy.count())]
    assert values == [0, 1], "account privacy is public/private only (FRIENDS is a video setting)"

    dlg.chk_privacy.setChecked(True)
    dlg.combo_privacy.setCurrentIndex(1)
    dlg._on_apply()
    assert repo.get_by_id(pid)["privacy"] == 1
