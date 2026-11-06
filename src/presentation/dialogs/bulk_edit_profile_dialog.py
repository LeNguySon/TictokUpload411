"""
Bulk Edit Profile Dialog for mass-updating project, status, country, note, and MMO settings.
Windows 11 Fluent Design styling.
"""

from typing import Any

from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CheckBox,
    ComboBox,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PrimaryPushButton,
    PushButton,
)

from src.infrastructure.database.repositories.profile_repository import (
    ProfileRepository,
)
from src.infrastructure.database.repositories.project_repository import (
    ProjectRepository,
)
from src.presentation.dialogs.dialog_helpers import (
    STANDARD_DIALOG_MARGINS,
    STANDARD_DIALOG_SPACING,
    create_dialog_header,
    fit_dialog_to_content,
)


class BulkEditProfileDialog(QDialog):
    """
    Dialog allowing mass updates across multiple profile records in a single transaction.
    Users toggle checkboxes to specify which attributes to overwrite.
    """

    def __init__(
        self,
        profile_ids: list[int],
        profile_repo: ProfileRepository,
        project_repo: ProjectRepository,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.profile_ids = profile_ids
        self.profile_repo = profile_repo
        self.project_repo = project_repo

        self.setWindowTitle("Cập Nhật Thông Tin Hàng Loạt")
        self.resize(520, 480)
        self._init_ui()
        fit_dialog_to_content(self)

    def exec(self) -> int:
        """Explicit Python wrapper over QDialog.exec for testability and lifecycle hooks."""
        return super().exec()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*STANDARD_DIALOG_MARGINS)
        layout.setSpacing(STANDARD_DIALOG_SPACING)

        count = len(self.profile_ids)
        header = create_dialog_header(
            icon=FluentIcon.EDIT,
            title=f"Cập nhật hàng loạt cho {count} hồ sơ đang chọn",
            subtitle="Tích chọn các trường thông tin bạn muốn ghi đè đồng loạt cho các tài khoản đã chọn.",
            parent=self,
        )
        layout.addWidget(header)

        form = QFormLayout()
        form.setSpacing(10)

        # 1. Project
        self.chk_project = CheckBox("Dự án / Nhóm:", self)
        self.combo_project = ComboBox(self)
        self.combo_project.addItem("Chưa gán dự án", userData=None)
        for proj in self.project_repo.list_all():
            self.combo_project.addItem(proj["name"], userData=proj["id"])
        self.combo_project.setEnabled(False)
        self.chk_project.toggled.connect(self.combo_project.setEnabled)
        form.addRow(self.chk_project, self.combo_project)

        # 2. Status
        self.chk_status = CheckBox("Trạng thái tài khoản:", self)
        self.combo_status = ComboBox(self)
        for stat in ("LIVE", "DIE", "CHECKPOINT", "stopped"):
            self.combo_status.addItem(stat, userData=stat)
        self.combo_status.setEnabled(False)
        self.chk_status.toggled.connect(self.combo_status.setEnabled)
        form.addRow(self.chk_status, self.combo_status)

        # 3. Country (QG)
        self.chk_qg = CheckBox("Quốc gia (QG):", self)
        self.input_qg = LineEdit(self)
        self.input_qg.setPlaceholderText("Ví dụ: US, UK, DE, VN, FR...")
        self.input_qg.setEnabled(False)
        self.chk_qg.toggled.connect(self.input_qg.setEnabled)
        form.addRow(self.chk_qg, self.input_qg)

        # 4. Privacy
        self.chk_privacy = CheckBox("Chế độ hiển thị:", self)
        self.combo_privacy = ComboBox(self)
        # Account privacy as stored by the collectors: 0 = public, 1 = private.
        for label, value in (("Công khai", 0), ("Riêng tư", 1)):
            self.combo_privacy.addItem(label, userData=value)
        self.combo_privacy.setEnabled(False)
        self.chk_privacy.toggled.connect(self.combo_privacy.setEnabled)
        form.addRow(self.chk_privacy, self.combo_privacy)

        # 5. Note
        self.chk_note = CheckBox("Ghi chú (Note):", self)
        self.input_note = LineEdit(self)
        self.input_note.setPlaceholderText("Nhập ghi chú áp dụng chung...")
        self.input_note.setEnabled(False)
        self.chk_note.toggled.connect(self.input_note.setEnabled)
        form.addRow(self.chk_note, self.input_note)

        layout.addLayout(form)
        layout.addStretch()

        # Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_apply = PrimaryPushButton("Áp Dụng Hàng Loạt", self)
        self.btn_apply.setIcon(FluentIcon.ACCEPT)
        self.btn_apply.clicked.connect(self._on_apply)

        self.btn_cancel = PushButton("Hủy", self)
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_apply)
        layout.addLayout(btn_layout)

    def _on_apply(self) -> None:
        payload: dict[str, Any] = {}

        if self.chk_project.isChecked():
            payload["project_id"] = self.combo_project.currentData()

        if self.chk_status.isChecked():
            payload["status"] = self.combo_status.currentData()

        if self.chk_qg.isChecked():
            payload["country"] = self.input_qg.text().strip().upper()

        if self.chk_privacy.isChecked():
            payload["privacy"] = self.combo_privacy.currentData()

        if self.chk_note.isChecked():
            payload["notes"] = self.input_note.text().strip()

        if not payload:
            InfoBar.warning(
                title="Chưa Chọn Trường Cần Đổi",
                content="Vui lòng tích chọn ít nhất 1 trường thông tin để cập nhật.",
                position=InfoBarPosition.TOP_RIGHT,
                parent=self,
            )
            return

        updated_count = self.profile_repo.bulk_update_fields(self.profile_ids, payload)
        if updated_count > 0:
            self.accept()
        else:
            InfoBar.warning(
                title="Cảnh Báo",
                content="Không có hồ sơ nào được cập nhật.",
                position=InfoBarPosition.TOP_RIGHT,
                parent=self,
            )
