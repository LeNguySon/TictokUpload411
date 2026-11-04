"""
Project / Campaign Manager Dialog for grouping profiles with Fluent styling.
Allows users to create new campaigns, rename existing projects, view aggregates,
and delete projects safely with zero direct cell click-editing.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QTableWidgetItem,
    QVBoxLayout,
)
from qfluentwidgets import (
    ColorPickerButton,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    TableWidget,
)

from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.presentation.widgets.table_helpers import (
    format_mmo_metric,
    format_money_string,
)


class ProjectManagerDialog(QDialog):
    """
    Dialog allowing users to create new campaigns, rename existing projects,
    view performance aggregates, and delete projects safely.
    Cell clicking does not directly edit data; editing is handled through dedicated actions.
    """

    def __init__(self, project_repo: ProjectRepository, parent=None) -> None:
        super().__init__(parent)
        self.project_repo = project_repo
        self.setWindowTitle("Quản Lý Dự Án & Chiến Dịch")
        self.resize(750, 480)
        self._init_ui()
        self.refresh_projects()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Top Form: Add new project
        row1 = QHBoxLayout()
        self.name_input = LineEdit(self)
        self.name_input.setPlaceholderText("Tên dự án mới (ví dụ: Nhóm Japan, Nhóm Hàn Quốc)...")
        self.color_picker = ColorPickerButton(Qt.GlobalColor.blue, "Màu thẻ", self)
        self.btn_create = PrimaryPushButton(FluentIcon.ADD, "Tạo Dự Án", self)
        self.btn_create.clicked.connect(self._on_create_project)

        row1.addWidget(QLabel("Tên dự án:"))
        row1.addWidget(self.name_input, 1)
        row1.addWidget(self.color_picker)
        row1.addWidget(self.btn_create)
        layout.addLayout(row1)

        # Table of existing projects with aggregates (Read-only on direct click)
        self.table = TableWidget(self)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            [
                "ID",
                "Tên Dự Án",
                "Tổng Profiles",
                "Số Acc LIVE",
                "Tổng Lượt View",
                "Tổng $ Earned",
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(TableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(TableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(lambda _: self._on_edit_project_name())
        layout.addWidget(self.table)

        # Bottom Actions
        bottom_layout = QHBoxLayout()
        self.btn_edit = PushButton(FluentIcon.EDIT, "Sửa Tên Dự Án", self)
        self.btn_edit.clicked.connect(self._on_edit_project_name)

        self.btn_delete = PushButton(FluentIcon.DELETE, "Xóa Dự Án Đã Chọn", self)
        self.btn_delete.clicked.connect(self._on_delete_selected)

        self.btn_close = PushButton("Đóng", self)
        self.btn_close.clicked.connect(self.accept)

        bottom_layout.addWidget(self.btn_edit)
        bottom_layout.addWidget(self.btn_delete)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_close)
        layout.addLayout(bottom_layout)

    def refresh_projects(self) -> None:
        """Fetches campaign aggregates and populates the table without inline editable flags."""
        aggregates = self.project_repo.get_project_aggregates()
        self.table.setRowCount(len(aggregates))

        for row_idx, agg in enumerate(aggregates):

            def make_item(text: str, align=Qt.AlignmentFlag.AlignCenter):
                item = QTableWidgetItem(str(text))
                item.setTextAlignment(align)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                return item

            self.table.setItem(row_idx, 0, make_item(agg["project_id"]))
            self.table.setItem(
                row_idx,
                1,
                make_item(
                    agg["project_name"],
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                ),
            )
            self.table.setItem(row_idx, 2, make_item(agg["total_profiles"]))
            self.table.setItem(row_idx, 3, make_item(agg["live_profiles"]))
            self.table.setItem(
                row_idx,
                4,
                make_item(
                    format_mmo_metric(agg["total_views"]),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                ),
            )
            self.table.setItem(
                row_idx,
                5,
                make_item(
                    format_money_string(agg["total_earned"]),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                ),
            )

    def _on_create_project(self) -> None:
        name = self.name_input.text().strip()
        if not name:
            return
        color_hex = self.color_picker.color.name()
        self.project_repo.create(name=name, color=color_hex)
        self.name_input.clear()
        self.refresh_projects()

    def _on_edit_project_name(self) -> None:
        """Prompts user to rename the selected project and updates repository."""
        selected_rows = {index.row() for index in self.table.selectedIndexes()}
        if not selected_rows:
            InfoBar.warning(
                title="Chưa chọn dự án",
                content="Vui lòng click chọn 1 dự án trong bảng để sửa tên.",
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return

        row = list(selected_rows)[0]
        id_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        if not id_item or not id_item.text().isdigit() or not name_item:
            return

        proj_id = int(id_item.text())
        current_name = name_item.text().strip()

        new_name, ok = QInputDialog.getText(
            self,
            "Sửa Tên Dự Án / Nhóm",
            f"Nhập tên mới cho dự án #{proj_id}:",
            text=current_name,
        )
        if ok and new_name.strip():
            self.project_repo.update(proj_id, name=new_name.strip())
            self.refresh_projects()
            InfoBar.success(
                title="Đã Cập Nhật",
                content=f"Đã đổi tên dự án #{proj_id} thành '{new_name.strip()}'.",
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_delete_selected(self) -> None:
        selected_rows = {index.row() for index in self.table.selectedIndexes()}
        for row in selected_rows:
            id_item = self.table.item(row, 0)
            if id_item and id_item.text().isdigit():
                proj_id = int(id_item.text())
                self.project_repo.safe_delete(proj_id)
        self.refresh_projects()
