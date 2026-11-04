"""
Trash Dialog for managing soft-deleted profiles and restoring them.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidgetItem,
    QVBoxLayout,
)
from qfluentwidgets import (
    InfoBar,
    InfoBarPosition,
    PrimaryPushButton,
    PushButton,
    TableWidget,
)

from src.infrastructure.database.connection import db_session
from src.infrastructure.database.repositories.profile_repository import ProfileRepository


class TrashDialog(QDialog):
    """
    Recycle Bin Dialog displaying soft-deleted TikTok profiles with restore capability.
    """

    def __init__(self, profile_repo: ProfileRepository, parent=None) -> None:
        super().__init__(parent)
        self.profile_repo = profile_repo

        self.setWindowTitle("Thùng Rác - Phục Hồi Hồ Sơ TikTok")
        self.resize(700, 450)
        self._init_ui()
        self.refresh_trash()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Danh sách các hồ sơ TikTok đã xóa tạm (Soft-deleted):"))

        self.table = TableWidget(self)
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

    def _list_trashed(self) -> list[dict]:
        with db_session(self.profile_repo.db_path, write=False) as conn:
            rows = conn.execute("SELECT * FROM profiles WHERE is_trashed = 1 ORDER BY id DESC;").fetchall()
            return [dict(r) for r in rows]

    def refresh_trash(self) -> None:
        trashed = self._list_trashed()
        self.table.setRowCount(len(trashed))

        for row_idx, p in enumerate(trashed):

            def make_item(text: str, align=Qt.AlignmentFlag.AlignCenter):
                item = QTableWidgetItem(str(text))
                item.setTextAlignment(align)
                return item

            self.table.setItem(row_idx, 0, make_item(p["id"]))
            self.table.setItem(
                row_idx, 1, make_item(p["name"], Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            )
            self.table.setItem(row_idx, 2, make_item(p.get("username_on_tiktok") or "-"))
            self.table.setItem(row_idx, 3, make_item(p.get("email") or "-"))
            self.table.setItem(row_idx, 4, make_item(p.get("status") or "stopped"))

    def _on_restore_selected(self) -> None:
        selected_rows = {index.row() for index in self.table.selectedIndexes()}
        restored_count = 0
        for row in selected_rows:
            id_item = self.table.item(row, 0)
            if id_item and id_item.text().isdigit():
                prof_id = int(id_item.text())
                if self.profile_repo.restore(prof_id):
                    restored_count += 1

        self.refresh_trash()
        InfoBar.success(
            title="Đã Phục Hồi",
            content=f"Đã phục hồi {restored_count} hồ sơ trở lại danh sách hoạt động.",
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _on_empty_trash(self) -> None:
        with db_session(self.profile_repo.db_path) as conn:
            cur = conn.execute("DELETE FROM profiles WHERE is_trashed = 1;")
            deleted = cur.rowcount

        self.refresh_trash()
        InfoBar.info(
            title="Dọn Sạch",
            content=f"Đã xóa vĩnh viễn {deleted} hồ sơ.",
            position=InfoBarPosition.TOP,
            parent=self,
        )
