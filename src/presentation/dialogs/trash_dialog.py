"""
Trash Dialog for managing soft-deleted profiles and restoring them.

All DB work runs on the UI thread pool (run_task); results come back on the GUI thread and are
dropped if the dialog was closed meanwhile.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PyQt6 import sip
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    MessageBox,
    PrimaryPushButton,
    PushButton,
    TableWidget,
)

from src.application.workers.task_worker import run_task
from src.infrastructure.database.connection import db_session
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.presentation.dialogs.dialog_cache import ReusableDialogMixin
from src.presentation.dialogs.dialog_helpers import (
    STANDARD_DIALOG_MARGINS,
    STANDARD_DIALOG_SPACING,
    create_dialog_header,
)
from src.presentation.widgets.fast_table import FastTableWidget

logger = logging.getLogger(__name__)


def list_trashed_profiles(db_path: Path | str) -> list[dict[str, Any]]:
    """Soft-deleted profiles, newest first (pure DB read)."""
    with db_session(db_path, write=False) as conn:
        rows = conn.execute("SELECT * FROM profiles WHERE is_trashed = 1 ORDER BY id DESC;").fetchall()
        return [dict(r) for r in rows]


def restore_profiles(profile_repo: ProfileRepository, profile_ids: list[int]) -> int:
    """Restores the given profiles; returns how many were restored."""
    return sum(1 for pid in profile_ids if profile_repo.restore(pid))


def purge_trashed_profiles(db_path: Path | str) -> int:
    """Permanently deletes every soft-deleted profile; returns the number of rows removed."""
    with db_session(db_path) as conn:
        cur = conn.execute("DELETE FROM profiles WHERE is_trashed = 1;")
        return int(cur.rowcount)


def confirm_permanent_delete(parent: QWidget, count: int) -> bool:
    """Asks before an irreversible purge of the trash."""
    box = MessageBox(
        "Xóa Vĩnh Viễn?",
        f"Xóa vĩnh viễn {count} hồ sơ trong thùng rác? Thao tác này KHÔNG thể hoàn tác.",
        parent,
    )
    return bool(box.exec())


class TrashDialog(ReusableDialogMixin, QDialog):
    """
    Recycle Bin Dialog displaying soft-deleted TikTok profiles with restore capability.
    """

    def __init__(self, profile_repo: ProfileRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.profile_repo = profile_repo
        self._closed = False

        self.setWindowTitle("Thùng Rác - Phục Hồi Hồ Sơ TikTok")
        self.resize(700, 450)
        self._init_ui()
        self.refresh_trash()

    def exec(self) -> int:
        """Explicit Python wrapper over QDialog.exec for testability and lifecycle hooks."""
        return super().exec()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*STANDARD_DIALOG_MARGINS)
        layout.setSpacing(STANDARD_DIALOG_SPACING)

        header = create_dialog_header(
            icon=FluentIcon.DELETE,
            title="Thùng Rác - Phục Hồi Hồ Sơ TikTok",
            subtitle="Quản lý và khôi phục các tài khoản đã bị xóa tạm hoặc dọn sạch vĩnh viễn.",
            parent=self,
        )
        layout.addWidget(header)

        self.table = FastTableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["ID", "Tên hồ sơ", "ID Tiktok", "Email", "Trạng thái"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(TableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        self.btn_restore = PrimaryPushButton("Phục Hồi Hồ Sơ Đã Chọn", self)
        self.btn_restore.clicked.connect(self._on_restore_selected)

        self.btn_empty = PushButton("Dọn Sạch Thùng Rác", self)
        self.btn_empty.clicked.connect(self._on_empty_trash)

        self.btn_close = PushButton("Đóng", self)
        self.btn_close.clicked.connect(self.accept)

        btn_layout.addWidget(self.btn_restore)
        btn_layout.addWidget(self.btn_empty)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

    def _alive(self) -> bool:
        return not self._closed and not sip.isdeleted(self)

    def _run(self, fn: Callable[..., Any], *args: Any, on_result: Callable[[Any], None], title: str) -> None:
        """Runs ``fn`` off the GUI thread; the callback runs on the GUI thread only if still open."""

        def ok(value: Any) -> None:
            if self._alive():
                on_result(value)

        def failed(err: str) -> None:
            logger.warning("%s failed: %s", title, err)
            if self._alive():
                InfoBar.error(title=title, content=err, position=InfoBarPosition.TOP, parent=self)

        run_task(fn, *args, on_result=ok, on_error=failed)

    def done(self, result: int) -> None:
        self._closed = True
        super().done(result)

    def closeEvent(self, event: QCloseEvent | None) -> None:
        self._closed = True
        super().closeEvent(event)

    def prepare_reopen(self) -> None:
        """Reused by the main window (DialogCache): accept results again and reload the trash."""
        self._closed = False
        self.refresh_trash()

    def refresh_trash(self) -> None:
        self._run(list_trashed_profiles, self.profile_repo.db_path, on_result=self._render_trash, title="Lỗi Thùng Rác")

    def _render_trash(self, trashed: list[dict[str, Any]]) -> None:
        self.table.setRowCount(len(trashed))

        def make_item(text: str, align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignCenter) -> QTableWidgetItem:
            item = QTableWidgetItem(str(text))
            item.setTextAlignment(align)
            return item

        for row_idx, p in enumerate(trashed):
            self.table.setItem(row_idx, 0, make_item(p["id"]))
            self.table.setItem(
                row_idx, 1, make_item(p["name"], Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            )
            self.table.setItem(row_idx, 2, make_item(p.get("username_on_tiktok") or "-"))
            self.table.setItem(row_idx, 3, make_item(p.get("email") or "-"))
            self.table.setItem(row_idx, 4, make_item(p.get("status") or "stopped"))

    def _on_restore_selected(self) -> None:
        selected_rows = {index.row() for index in self.table.selectedIndexes()}
        ids: list[int] = []
        for row in selected_rows:
            id_item = self.table.item(row, 0)
            if id_item and id_item.text().isdigit():
                ids.append(int(id_item.text()))
        if not ids:
            return

        def restored(count: int) -> None:
            self.refresh_trash()
            InfoBar.success(
                title="Đã Phục Hồi",
                content=f"Đã phục hồi {count} hồ sơ trở lại danh sách hoạt động.",
                position=InfoBarPosition.TOP,
                parent=self,
            )

        self._run(restore_profiles, self.profile_repo, ids, on_result=restored, title="Lỗi Phục Hồi")

    def _on_empty_trash(self) -> None:
        count = self.table.rowCount()
        if count == 0 or not confirm_permanent_delete(self, count):
            return

        def purged(deleted: int) -> None:
            self.refresh_trash()
            InfoBar.info(
                title="Dọn Sạch",
                content=f"Đã xóa vĩnh viễn {deleted} hồ sơ.",
                position=InfoBarPosition.TOP,
                parent=self,
            )

        self._run(purge_trashed_profiles, self.profile_repo.db_path, on_result=purged, title="Lỗi Dọn Thùng Rác")
