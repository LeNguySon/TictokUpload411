"""
Assign Project Dialog for moving / grouping profiles into projects.
Fluent Design styling with vector icons.
"""

from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QVBoxLayout,
)
from qfluentwidgets import (
    ComboBox,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
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
)


class AssignProjectDialog(QDialog):
    """
    Dialog allowing users to assign one or multiple profiles to a project/campaign.
    """

    def __init__(
        self,
        profile_ids: list[int],
        profile_repo: ProfileRepository,
        project_repo: ProjectRepository,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.profile_ids = profile_ids
        self.profile_repo = profile_repo
        self.project_repo = project_repo

        self.setWindowTitle("Chuyển Dự Án / Chiến Dịch")
        self.resize(480, 230)
        self._init_ui()
        self._populate_projects()

    def exec(self) -> int:
        """Explicit Python wrapper over QDialog.exec for testability and lifecycle hooks."""
        return super().exec()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*STANDARD_DIALOG_MARGINS)
        layout.setSpacing(STANDARD_DIALOG_SPACING)

        count = len(self.profile_ids)
        title_text = f"Chuyển {count} hồ sơ sang Dự án" if count > 1 else "Chuyển hồ sơ sang Dự án"
        header = create_dialog_header(
            icon=FluentIcon.FOLDER,
            title=title_text,
            subtitle="Chọn dự án / nhóm chiến dịch đích cho các tài khoản đang chọn.",
            parent=self,
        )
        layout.addWidget(header)

        # Project ComboBox
        self.combo_project = ComboBox(self)
        self.combo_project.setMinimumHeight(34)
        layout.addWidget(self.combo_project)

        layout.addStretch()

        # Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_apply = PrimaryPushButton("Áp Dụng", self)
        self.btn_apply.setIcon(FluentIcon.ACCEPT)
        self.btn_apply.clicked.connect(self._on_apply)

        self.btn_cancel = PushButton("Hủy", self)
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_apply)
        layout.addLayout(btn_layout)

    def _populate_projects(self) -> None:
        self.combo_project.clear()
        self.combo_project.addItem("📁 Không phân nhóm (Chưa gán dự án)", userData=None)

        projects = self.project_repo.list_all()
        for p in projects:
            self.combo_project.addItem(f"📁 {p['name']}", userData=p["id"])

    def _on_apply(self) -> None:
        chosen_project_id = self.combo_project.currentData()
        updated_count = self.profile_repo.bulk_assign_project(self.profile_ids, chosen_project_id)

        if updated_count > 0:
            self.accept()
        else:
            InfoBar.warning(
                title="Cảnh Báo",
                content="Không có hồ sơ nào được cập nhật.",
                position=InfoBarPosition.TOP_RIGHT,
                parent=self,
            )
