"""
Project / Campaign Manager Dialog for grouping profiles with Fluent styling.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidgetItem,
    QVBoxLayout,
)
from qfluentwidgets import (
    ColorPickerButton,
    FluentIcon,
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
    Dialog allowing users to create new campaigns, view aggregates, and delete projects safely.
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

        # Top Form: Add new project with video folder
        form_layout = QVBoxLayout()
        row1 = QHBoxLayout()
        self.name_input = LineEdit(self)
        self.name_input.setPlaceholderText("Tên dự án mới (ví dụ: Nhóm Japan, Nhóm Hàn Quốc)...")
        self.color_picker = ColorPickerButton(Qt.GlobalColor.blue, "Màu thẻ", self)

        row1.addWidget(QLabel("Tên dự án:"))
        row1.addWidget(self.name_input, 1)
        row1.addWidget(self.color_picker)
        form_layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.folder_input = LineEdit(self)
        self.folder_input.setPlaceholderText("Thư mục chứa video của nhóm (ví dụ: D:\\videos\\Japan)...")
        self.btn_browse = PushButton(FluentIcon.FOLDER, "Chọn Thư Mục...", self)
        self.btn_browse.clicked.connect(self._on_browse_folder)

        self.btn_create = PrimaryPushButton("Tạo Dự Án", self)
        self.btn_create.clicked.connect(self._on_create_project)

        row2.addWidget(QLabel("Kho video:"))
        row2.addWidget(self.folder_input, 1)
        row2.addWidget(self.btn_browse)
        row2.addWidget(self.btn_create)
        form_layout.addLayout(row2)

        layout.addLayout(form_layout)

        # Table of existing projects with aggregates
        self.table = TableWidget(self)
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            [
                "ID",
                "Tên Dự Án",
                "Thư Mục Video",
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
        layout.addWidget(self.table)

        # Bottom Actions
        bottom_layout = QHBoxLayout()
        self.btn_delete = PushButton("Xóa Dự Án Đã Chọn", self)
        self.btn_delete.clicked.connect(self._on_delete_selected)
        self.btn_close = PushButton("Đóng", self)
        self.btn_close.clicked.connect(self.accept)

        bottom_layout.addWidget(self.btn_delete)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_close)
        layout.addLayout(bottom_layout)

    def _on_browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục video cho nhóm/dự án")
        if folder:
            self.folder_input.setText(folder)

    def refresh_projects(self) -> None:
        """Fetches campaign aggregates and populates the table."""
        aggregates = self.project_repo.get_project_aggregates()
        self.table.setRowCount(len(aggregates))

        for row_idx, agg in enumerate(aggregates):

            def make_item(text: str, align=Qt.AlignmentFlag.AlignCenter):
                item = QTableWidgetItem(str(text))
                item.setTextAlignment(align)
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
            self.table.setItem(
                row_idx,
                2,
                make_item(
                    agg.get("video_folder") or "Mặc định",
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                ),
            )
            self.table.setItem(row_idx, 3, make_item(agg["total_profiles"]))
            self.table.setItem(row_idx, 4, make_item(agg["live_profiles"]))
            self.table.setItem(
                row_idx,
                5,
                make_item(
                    format_mmo_metric(agg["total_views"]),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                ),
            )
            self.table.setItem(
                row_idx,
                6,
                make_item(
                    format_money_string(agg["total_earned"]),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                ),
            )

    def _on_create_project(self) -> None:
        name = self.name_input.text().strip()
        if not name:
            return
        folder = self.folder_input.text().strip() or None
        color_hex = self.color_picker.color.name()
        self.project_repo.create(name=name, color=color_hex, video_folder=folder)
        self.name_input.clear()
        self.folder_input.clear()
        self.refresh_projects()

    def _on_delete_selected(self) -> None:
        selected_rows = {index.row() for index in self.table.selectedIndexes()}
        for row in selected_rows:
            id_item = self.table.item(row, 0)
            if id_item and id_item.text().isdigit():
                proj_id = int(id_item.text())
                self.project_repo.safe_delete(proj_id)
        self.refresh_projects()
