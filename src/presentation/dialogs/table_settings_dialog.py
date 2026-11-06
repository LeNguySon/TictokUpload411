"""
Table Settings Dialog for configuring 28-column visibility preferences with Fluent design.
"""

from PyQt6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CheckBox,
    FluentIcon,
    PrimaryPushButton,
    PushButton,
)

from src.presentation.dialogs.dialog_helpers import (
    STANDARD_DIALOG_MARGINS,
    STANDARD_DIALOG_SPACING,
    create_dialog_header,
)
from src.presentation.widgets.table_helpers import get_profile_table_headers


class TableSettingsDialog(QDialog):
    """
    Dialog allowing creators to show or hide specific columns in the 28-column profile table.
    """

    def __init__(self, hidden_columns: set[int] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.headers = get_profile_table_headers()
        self.hidden_columns: set[int] = set(hidden_columns or set())
        self._checkboxes: dict[int, CheckBox] = {}

        self.setWindowTitle("Cài Đặt Cột Bảng Hồ Sơ (28 Cột MMO)")
        self.resize(620, 600)  # 29 Fluent checkboxes fit without a scrollbar
        self._init_ui()

    def exec(self) -> int:
        """Explicit Python wrapper over QDialog.exec for testability and lifecycle hooks."""
        return super().exec()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*STANDARD_DIALOG_MARGINS)
        layout.setSpacing(STANDARD_DIALOG_SPACING)

        header = create_dialog_header(
            icon=FluentIcon.SETTING,
            title="Cài Đặt Cột Bảng Hồ Sơ (28 Cột MMO)",
            subtitle="Tùy biến hiển thị/ẩn các cột dữ liệu theo nhu cầu quản trị tài khoản.",
            parent=self,
        )
        layout.addWidget(header)

        # Scroll Area for 29 columns
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        container = QWidget()
        grid = QGridLayout(container)
        grid.setSpacing(8)

        # 3 columns layout
        for idx, column_name in enumerate(self.headers):
            chk = CheckBox(f"{idx}. {column_name}", container)
            chk.setChecked(idx not in self.hidden_columns)
            self._checkboxes[idx] = chk
            row = idx // 3
            col = idx % 3
            grid.addWidget(chk, row, col)

        scroll.setWidget(container)
        layout.addWidget(scroll)

        # Quick toggles
        top_btn_layout = QHBoxLayout()
        btn_select_all = PushButton("Chọn Tất Cả", self)
        btn_select_all.clicked.connect(self._on_select_all)
        btn_reset = PushButton("Mặc Định", self)
        btn_reset.clicked.connect(self._on_reset)
        top_btn_layout.addWidget(btn_select_all)
        top_btn_layout.addWidget(btn_reset)
        top_btn_layout.addStretch()
        layout.addLayout(top_btn_layout)

        # Bottom Actions
        btn_layout = QHBoxLayout()
        self.btn_save = PrimaryPushButton("Lưu Cài Đặt", self)
        self.btn_save.clicked.connect(self._on_save)
        self.btn_cancel = PushButton("Hủy", self)
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        layout.addLayout(btn_layout)

    def _on_select_all(self) -> None:
        for chk in self._checkboxes.values():
            chk.setChecked(True)

    def _on_reset(self) -> None:
        for chk in self._checkboxes.values():
            chk.setChecked(True)

    def _on_save(self) -> None:
        self.hidden_columns = {idx for idx, chk in self._checkboxes.items() if not chk.isChecked()}
        self.accept()
