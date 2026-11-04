"""
Table Settings Dialog for configuring 28-column visibility preferences with Fluent design.
"""

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    PrimaryPushButton,
    PushButton,
)

from src.presentation.widgets.table_helpers import get_profile_table_headers


class TableSettingsDialog(QDialog):
    """
    Dialog allowing creators to show or hide specific columns in the 28-column profile table.
    """

    def __init__(self, hidden_columns: set[int] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.headers = get_profile_table_headers()
        self.hidden_columns: set[int] = set(hidden_columns or set())
        self._checkboxes: dict[int, QCheckBox] = {}

        self.setWindowTitle("Cài Đặt Cột Bảng Hồ Sơ (28 Cột MMO)")
        self.resize(600, 480)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Tích chọn các cột bạn muốn hiển thị trên giao diện chính:"))

        # Scroll Area for 29 columns
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        container = QWidget()
        grid = QGridLayout(container)
        grid.setSpacing(8)

        # 3 columns layout
        for idx, header in enumerate(self.headers):
            chk = QCheckBox(f"{idx}. {header}", container)
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
