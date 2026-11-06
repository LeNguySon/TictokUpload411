"""
Batch Folder Upload Dialog: Allows multi-project directory scanning, multi-profile fair-share distribution,
golden hour scheduling, spintax templating, and automated batch upload triggering.
Conforms to Gloglin2609 & SamMonny UI/UX standards with Fluent UI styling.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QThreadPool, QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CheckBox,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    SpinBox,
)

from src.application.services.upload_service import UploadService
from src.application.workers.folder_distribution_worker import FolderDistributionWorker
from src.application.workers.task_worker import run_task
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.presentation.dialogs.dialog_helpers import (
    STANDARD_DIALOG_MARGINS,
    STANDARD_DIALOG_SPACING,
    create_dialog_header,
    style_group_box,
    style_plain_table,
)
from src.presentation.widgets.table_helpers import h_header, v_header

logger = logging.getLogger(__name__)


FOLDER_SCAN_DEBOUNCE_MS = 300
SCANNING_TEXT = "⏳ Đang quét..."


def scan_text_for(folder: str, count: int) -> str:
    return f"{count} video" if folder and count > 0 else ("0 video" if folder else "Chưa chọn")


def count_valid_videos_in_folder(folder_path: str) -> int:
    """Scans folder recursively and counts valid non-posted video files."""
    if not folder_path:
        return 0
    p = Path(folder_path)
    if not p.is_dir():
        return 0
    valid_exts = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
    try:
        return sum(
            1
            for f in p.rglob("*")
            if f.is_file()
            and f.suffix.lower() in valid_exts
            and not any(part in ("_posted", ".posted") for part in f.parts)
        )
    except Exception:
        return 0


class BatchFolderUploadDialog(QDialog):
    """
    Comprehensive dialog for bulk folder scanning, multi-project folder management,
    deduplication, Spintax captions, and fair-share round-robin distribution to TikTok accounts.
    """

    def __init__(
        self,
        profile_repo: ProfileRepository,
        upload_service: UploadService,
        initial_folder: str | None = None,
        project_id: int | None = None,
        project_name: str | None = None,
        project_repo: ProjectRepository | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        # Folder scans (recursive rglob) run on the UI pool; generations drop stale results (T7).
        self._scan_gen = 0
        self._pending_scan_folder = ""
        self._row_scan_gen: dict[int, int] = {}
        self._scan_debounce = QTimer(self)
        self._scan_debounce.setSingleShot(True)
        self._scan_debounce.setInterval(FOLDER_SCAN_DEBOUNCE_MS)
        self._scan_debounce.timeout.connect(self._start_folder_scan)
        self.profile_repo = profile_repo
        self.upload_service = upload_service
        self.project_repo = project_repo or ProjectRepository(profile_repo.db_path)
        self.initial_folder = initial_folder
        self.project_id = project_id
        self.project_name = project_name
        self.distributed_videos: list[dict[str, Any]] = []
        self.auto_start_upload: bool = False
        self.worker: FolderDistributionWorker | None = None

        self.setWindowTitle("Nạp Thư Mục Phân Bổ (Batch Upload)")
        self.resize(850, 720)
        self._init_ui()
        self._load_projects_table()
        self._sync_profiles_for_selected_projects()

    def exec(self) -> int:
        """Explicit Python wrapper over QDialog.exec for testability and lifecycle hooks."""
        return super().exec()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(*STANDARD_DIALOG_MARGINS)
        main_layout.setSpacing(STANDARD_DIALOG_SPACING)

        header = create_dialog_header(
            icon=FluentIcon.FOLDER_ADD,
            title="Nạp Thư Mục Phân Bổ (Batch Upload)",
            subtitle="Quét video từ thư mục máy tính và tự động phân bổ đồng đều hoặc ngẫu nhiên vào các tài khoản/dự án.",
            parent=self,
        )
        main_layout.addWidget(header)

        # 0. Active Project Indicator Banner
        if self.project_id is not None:
            p_title = f"Chiến Dịch Mục Tiêu: <b>{self.project_name}</b> (Có thể tích chọn thêm các nhóm khác bên dưới)"
        else:
            p_title = "Chế Độ Phân Bổ: <b>Hỗ trợ phân bổ đồng thời nhiều Dự án / Nhóm theo thư mục riêng</b>"
        self.lbl_project_badge = QLabel(p_title, self)
        self.lbl_project_badge.setStyleSheet(
            "background-color: #F3F2F1; border: 1px solid #D2D0CE; border-radius: 6px; padding: 8px 12px; font-size: 13px; color: #0078D4;"
        )
        main_layout.addWidget(self.lbl_project_badge)

        # 1. Multi-Project Video Folders Table
        grp_projects = QGroupBox("1. Danh Sách Các Dự Án / Nhóm && Thư Mục Video Riêng (Multi-Project Folders)", self)
        style_group_box(grp_projects)
        layout_proj_v = QVBoxLayout(grp_projects)
        layout_proj_v.setSpacing(6)

        proj_btn_row = QHBoxLayout()
        self.btn_select_all_proj = PushButton("Chọn Tất Cả Nhóm", self)
        self.btn_select_all_proj.clicked.connect(self._select_all_projects)
        self.btn_deselect_all_proj = PushButton("Bỏ Chọn", self)
        self.btn_deselect_all_proj.clicked.connect(self._deselect_all_projects)
        self.lbl_proj_summary = QLabel("Đã chọn: 0 nhóm", self)
        self.lbl_proj_summary.setStyleSheet("font-size: 12px; color: #0078D4; font-weight: 600;")
        proj_btn_row.addWidget(self.btn_select_all_proj)
        proj_btn_row.addWidget(self.btn_deselect_all_proj)
        proj_btn_row.addStretch()
        proj_btn_row.addWidget(self.lbl_proj_summary)
        layout_proj_v.addLayout(proj_btn_row)

        self.project_table = style_plain_table(QTableWidget(self))
        self.project_table.setColumnCount(5)
        self.project_table.setHorizontalHeaderLabels(
            [
                "Chọn",
                "Dự Án / Nhóm",
                "Thư Mục Video Riêng",
                "Video Hợp Lệ",
                "Số Kênh LIVE",
            ]
        )
        h_header(self.project_table).setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h_header(self.project_table).setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h_header(self.project_table).setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h_header(self.project_table).setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h_header(self.project_table).setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        v_header(self.project_table).setVisible(False)
        # Rows host a LineEdit + button: give them room and show 3 rows without scrolling.
        v_header(self.project_table).setDefaultSectionSize(40)
        self.project_table.setMinimumHeight(40 * 3 + 34)
        layout_proj_v.addWidget(self.project_table)

        # Backward compatibility fields (synced transparently)
        self.txt_folder = LineEdit(self)
        self.txt_folder.setVisible(False)
        self.txt_folder.textChanged.connect(self._update_scanned_files_count)
        self.lbl_scan_info = QLabel("Chưa quét thư mục", self)
        self.lbl_scan_info.setVisible(False)

        main_layout.addWidget(grp_projects)

        # 2. Target Profiles Selection Group
        grp_profiles = QGroupBox("2. Danh Sách Tài Khoản Nhận Video Của Các Nhóm Đã Chọn (Target Profiles)", self)
        style_group_box(grp_profiles)
        layout_profiles = QVBoxLayout(grp_profiles)
        layout_profiles.setSpacing(6)

        btn_row = QHBoxLayout()
        self.btn_select_all = PushButton("Chọn Tất Cả", self)
        self.btn_select_all.clicked.connect(self._select_all_profiles)
        self.btn_deselect_all = PushButton("Bỏ Chọn", self)
        self.btn_deselect_all.clicked.connect(self._deselect_all_profiles)
        self.lbl_selected_count = QLabel("Đã chọn: 0 tài khoản", self)
        self.lbl_selected_count.setStyleSheet("font-size: 12px; color: #107C41; font-weight: 600;")
        btn_row.addWidget(self.btn_select_all)
        btn_row.addWidget(self.btn_deselect_all)
        btn_row.addStretch()
        btn_row.addWidget(self.lbl_selected_count)
        layout_profiles.addLayout(btn_row)

        self.profile_table = style_plain_table(QTableWidget(self))
        self.profile_table.setColumnCount(5)
        self.profile_table.setHorizontalHeaderLabels(["Chọn", "ID", "Dự Án / Nhóm", "Tên Tài Khoản", "Quốc Gia"])
        h_header(self.profile_table).setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h_header(self.profile_table).setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h_header(self.profile_table).setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h_header(self.profile_table).setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        h_header(self.profile_table).setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        v_header(self.profile_table).setVisible(False)
        self.profile_table.setMinimumHeight(120)
        layout_profiles.addWidget(self.profile_table)

        main_layout.addWidget(grp_profiles)

        # 3. Distribution & Publishing Options
        grp_opts = QGroupBox("3. Cấu Hình Phân Bổ && Lịch Đăng (Distribution Options)", self)
        style_group_box(grp_opts)
        layout_opts = QVBoxLayout(grp_opts)
        layout_opts.setSpacing(8)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Khoảng cách tối thiểu giữa các video (giờ):", self))
        self.spin_interval = SpinBox(self)
        self.spin_interval.setRange(1, 72)
        self.spin_interval.setValue(12)
        self.spin_interval.setMinimumWidth(140)
        row1.addWidget(self.spin_interval)
        row1.addStretch()
        layout_opts.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Spintax Tiêu Đề:", self))
        self.txt_spintax = LineEdit(self)
        self.txt_spintax.setPlaceholderText("Ví dụ: {Tuyệt đỉnh|Cực phẩm} video {hôm nay|mới nhất} {title} #fyp #viral")
        row2.addWidget(self.txt_spintax, 1)
        layout_opts.addLayout(row2)

        # Options grid (3 columns): distribution | interaction | quality & labels.
        # A single horizontal row clipped the labels ("Cho phép Due", "AI-Generatec").
        self.chk_shuffle = CheckBox("Xáo trộn thứ tự ngẫu nhiên", self)
        self.chk_shuffle.setChecked(True)
        self.chk_deduplicate = CheckBox("Khử trùng lặp (SHA-256)", self)
        self.chk_deduplicate.setChecked(True)
        self.chk_allow_hd = CheckBox("Upload chất lượng cao (HD)", self)
        self.chk_allow_hd.setChecked(True)
        self.chk_comment = CheckBox("Cho phép bình luận", self)
        self.chk_comment.setChecked(True)
        self.chk_duet = CheckBox("Cho phép Duet", self)
        self.chk_duet.setChecked(True)
        self.chk_stitch = CheckBox("Cho phép Stitch", self)
        self.chk_stitch.setChecked(True)
        self.chk_is_ai = CheckBox("Gắn nhãn AI-Generated", self)

        grid_opts = QGridLayout()
        grid_opts.setHorizontalSpacing(24)
        grid_opts.setVerticalSpacing(6)
        for idx, chk in enumerate(
            (
                self.chk_shuffle,
                self.chk_deduplicate,
                self.chk_allow_hd,
                self.chk_comment,
                self.chk_duet,
                self.chk_stitch,
                self.chk_is_ai,
            )
        ):
            grid_opts.addWidget(chk, idx // 3, idx % 3)
        grid_opts.setColumnStretch(3, 1)
        layout_opts.addLayout(grid_opts)

        main_layout.addWidget(grp_opts)

        # Progress Bar & Async Status (Guarantees zero GUI freeze)
        self.progress_bar = ProgressBar(self)
        self.progress_bar.setVisible(False)
        self.lbl_progress_status = QLabel("", self)
        self.lbl_progress_status.setVisible(False)
        self.lbl_progress_status.setStyleSheet("font-size: 12px; color: #0078D4; font-weight: 600;")
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(self.lbl_progress_status)

        # Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_cancel = PushButton("Hủy Bỏ", self)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)

        self.btn_schedule_only = PushButton("Lập Lịch Hàng Đợi (Queue Only)", self)
        self.btn_schedule_only.clicked.connect(self._on_schedule_only)

        self.btn_run_now = PrimaryPushButton("BẮT ĐẦU ĐĂNG NGAY (Run Now)", self)
        self.btn_run_now.clicked.connect(self._on_run_now)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_schedule_only)
        btn_layout.addWidget(self.btn_run_now)
        main_layout.addLayout(btn_layout)

    def _load_projects_table(self) -> None:
        """Loads projects into project_table with folder inputs and video counters."""
        aggregates = self.project_repo.get_aggregates()
        if not aggregates:
            projects = self.project_repo.list_all()
            aggregates = [
                {
                    "project_id": p["id"],
                    "project_name": p["name"],
                    "video_folder": p.get("video_folder"),
                    "total_profiles": 0,
                }
                for p in projects
            ]

        self.project_table.setRowCount(len(aggregates))
        for row, proj in enumerate(aggregates):
            p_id = proj["project_id"]
            p_name = proj["project_name"]
            folder = proj.get("video_folder") or ""
            if not folder and self.initial_folder and p_id == self.project_id:
                folder = self.initial_folder

            # Col 0: Checkbox
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk_item.setData(Qt.ItemDataRole.UserRole, p_id)
            if self.project_id is not None:
                chk_item.setCheckState(Qt.CheckState.Checked if p_id == self.project_id else Qt.CheckState.Unchecked)
            else:
                chk_item.setCheckState(Qt.CheckState.Checked)

            # Col 1: Project Name
            name_item = QTableWidgetItem(p_name)
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            name_item.setData(Qt.ItemDataRole.UserRole, p_id)

            # Col 2: Folder selector widget (LineEdit + Browse button)
            cell_widget = QWidget(self)
            cell_layout = QHBoxLayout(cell_widget)
            cell_layout.setContentsMargins(4, 2, 4, 2)
            cell_layout.setSpacing(6)

            folder_edit = LineEdit(cell_widget)
            folder_edit.setText(folder)
            folder_edit.setPlaceholderText("Dán hoặc chọn đường dẫn video của nhóm...")

            browse_btn = PushButton("Chọn...", cell_widget)
            browse_btn.clicked.connect(
                lambda _, r=row, pid=p_id, ed=folder_edit: self._on_browse_project_folder(r, pid, ed)
            )
            folder_edit.textChanged.connect(
                lambda text, r=row, pid=p_id: self._on_project_folder_text_changed(r, pid, text)
            )

            cell_layout.addWidget(folder_edit, 1)
            cell_layout.addWidget(browse_btn)

            # Col 3: Scanned valid videos count (filled asynchronously)
            scan_item = QTableWidgetItem(SCANNING_TEXT if folder else scan_text_for(folder, 0))
            scan_item.setFlags(Qt.ItemFlag.ItemIsEnabled)

            # Col 4: Total profiles in project
            prof_count = proj.get("total_profiles") or len(self.profile_repo.list_active(project_id=p_id))
            prof_item = QTableWidgetItem(f"{prof_count} tài khoản")
            prof_item.setFlags(Qt.ItemFlag.ItemIsEnabled)

            self.project_table.setItem(row, 0, chk_item)
            self.project_table.setItem(row, 1, name_item)
            self.project_table.setCellWidget(row, 2, cell_widget)
            self.project_table.setItem(row, 3, scan_item)
            if folder:
                self._scan_project_row(row, folder)
            self.project_table.setItem(row, 4, prof_item)

            # Sync initial folder to txt_folder if matching
            if row == 0 or (self.project_id is not None and p_id == self.project_id):
                self.txt_folder.setText(folder)
                self._update_scanned_files_count(folder)

        self.project_table.itemChanged.connect(self._on_project_table_item_changed)
        self._update_project_summary()

    def _on_browse_project_folder(self, row: int, project_id: int, edit: LineEdit) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Chọn Thư Mục Chứa Video", edit.text().strip() or "")
        if folder:
            edit.setText(folder)
            self._on_project_folder_text_changed(row, project_id, folder)

    def _on_project_folder_text_changed(self, row: int, project_id: int, text: str) -> None:
        folder = text.strip()
        item = self.project_table.item(row, 3)
        if item:
            item.setText(SCANNING_TEXT if folder else scan_text_for(folder, 0))
        if folder:
            self._scan_project_row(row, folder)
        if folder and Path(folder).is_dir():
            try:
                self.project_repo.update(project_id, video_folder=folder)
            except Exception as e:
                logger.debug("Auto-save project video folder notice: %s", e)
        self.txt_folder.setText(folder)
        self._update_scanned_files_count(folder)

    def _on_project_table_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 0:
            self._update_project_summary()
            self._sync_profiles_for_selected_projects()

    def _select_all_projects(self) -> None:
        self.project_table.blockSignals(True)
        for row in range(self.project_table.rowCount()):
            item = self.project_table.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Checked)
        self.project_table.blockSignals(False)
        self._update_project_summary()
        self._sync_profiles_for_selected_projects()

    def _deselect_all_projects(self) -> None:
        self.project_table.blockSignals(True)
        for row in range(self.project_table.rowCount()):
            item = self.project_table.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Unchecked)
        self.project_table.blockSignals(False)
        self._update_project_summary()
        self._sync_profiles_for_selected_projects()

    def _update_project_summary(self) -> None:
        count = 0
        for row in range(self.project_table.rowCount()):
            item = self.project_table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                count += 1
        self.lbl_proj_summary.setText(f"Đã chọn: {count} nhóm")

    def _sync_profiles_for_selected_projects(self) -> None:
        """Loads and syncs target profiles for all checked projects."""
        selected_project_ids = []
        for row in range(self.project_table.rowCount()):
            item = self.project_table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                p_id = item.data(Qt.ItemDataRole.UserRole)
                if p_id is not None:
                    selected_project_ids.append(p_id)

        all_projects = {p["id"]: p["name"] for p in self.project_repo.list_all()}
        all_profiles = []

        if self.project_id is not None:
            all_profiles = self.profile_repo.list_active(project_id=self.project_id)
            if not all_profiles:
                all_profiles = self.profile_repo.list_all()
        else:
            default_proj = self.project_repo.get_default_project()
            default_pid = default_proj["id"] if default_proj else 1
            seen_ids = set()

            for p_id in selected_project_ids:
                profs = self.profile_repo.list_active(project_id=p_id)
                # If default project is selected, also include unassigned profiles
                if p_id == default_pid:
                    unassigned = [p for p in self.profile_repo.list_all() if p.get("project_id") is None]
                    profs.extend(unassigned)
                for p in profs:
                    if p["id"] not in seen_ids:
                        seen_ids.add(p["id"])
                        all_profiles.append(p)

            if not all_profiles:
                all_profiles = self.profile_repo.list_all()

        self.profile_table.blockSignals(True)
        self.profile_table.setRowCount(len(all_profiles))
        for row, p in enumerate(all_profiles):
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk_item.setCheckState(Qt.CheckState.Checked)
            chk_item.setData(Qt.ItemDataRole.UserRole, p.get("project_id"))

            id_item = QTableWidgetItem(str(p["id"]))
            id_item.setFlags(Qt.ItemFlag.ItemIsEnabled)

            proj_name = all_projects.get(p.get("project_id")) or "Mặc định"
            proj_item = QTableWidgetItem(proj_name)
            proj_item.setFlags(Qt.ItemFlag.ItemIsEnabled)

            name_item = QTableWidgetItem(p.get("name") or p.get("account") or f"Profile #{p['id']}")
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled)

            country_item = QTableWidgetItem(p.get("country") or "US")
            country_item.setFlags(Qt.ItemFlag.ItemIsEnabled)

            self.profile_table.setItem(row, 0, chk_item)
            self.profile_table.setItem(row, 1, id_item)
            self.profile_table.setItem(row, 2, proj_item)
            self.profile_table.setItem(row, 3, name_item)
            self.profile_table.setItem(row, 4, country_item)

        self.profile_table.blockSignals(False)
        self._update_selected_count()

    def _select_all_profiles(self) -> None:
        self.profile_table.blockSignals(True)
        for row in range(self.profile_table.rowCount()):
            item = self.profile_table.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Checked)
        self.profile_table.blockSignals(False)
        self._update_selected_count()

    def _deselect_all_profiles(self) -> None:
        self.profile_table.blockSignals(True)
        for row in range(self.profile_table.rowCount()):
            item = self.profile_table.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Unchecked)
        self.profile_table.blockSignals(False)
        self._update_selected_count()

    def _update_selected_count(self) -> None:
        count = len(self.get_selected_profile_ids())
        self.lbl_selected_count.setText(f"Đã chọn: {count} tài khoản")

    def get_selected_profile_ids(self) -> list[int]:
        pids: list[int] = []
        for row in range(self.profile_table.rowCount()):
            chk = self.profile_table.item(row, 0)
            id_item = self.profile_table.item(row, 1)
            if chk and chk.checkState() == Qt.CheckState.Checked and id_item:
                try:
                    pids.append(int(id_item.text()))
                except ValueError:
                    pass
        return pids

    def get_selected_project_batches(self) -> list[dict[str, Any]]:
        """Extracts configuration batches for all checked projects in the project_table."""
        batches: list[dict[str, Any]] = []
        for row in range(self.project_table.rowCount()):
            chk = self.project_table.item(row, 0)
            if not chk or chk.checkState() != Qt.CheckState.Checked:
                continue

            p_id = chk.data(Qt.ItemDataRole.UserRole)
            name_item = self.project_table.item(row, 1)
            raw_name = name_item.text().replace("🏷️ ", "") if name_item else f"Project #{p_id}"

            cell_widget = self.project_table.cellWidget(row, 2)
            f_edit = cell_widget.findChild(LineEdit) if cell_widget else None
            f_path = f_edit.text().strip() if f_edit else ""

            # Resolve assigned profile IDs for this project that are checked in profile_table
            selected_pids = []
            for p_row in range(self.profile_table.rowCount()):
                p_chk = self.profile_table.item(p_row, 0)
                if p_chk and p_chk.checkState() == Qt.CheckState.Checked:
                    if p_chk.data(Qt.ItemDataRole.UserRole) == p_id:
                        id_item = self.profile_table.item(p_row, 1)
                        if id_item:
                            try:
                                selected_pids.append(int(id_item.text()))
                            except ValueError:
                                pass

            # Fallback to active profiles of project if not displayed
            if not selected_pids and p_id is not None:
                selected_pids = [p["id"] for p in self.profile_repo.list_active(project_id=p_id)]

            if f_path and Path(f_path).is_dir() and selected_pids:
                batches.append(
                    {
                        "project_id": p_id,
                        "project_name": raw_name,
                        "folder_path": f_path,
                        "profile_ids": selected_pids,
                    }
                )

        return batches

    def _scan_project_row(self, row: int, folder: str) -> None:
        """Counts videos of one project folder off the GUI thread; only the latest scan per row is shown."""
        gen = self._row_scan_gen.get(row, 0) + 1
        self._row_scan_gen[row] = gen

        def _apply(count: int) -> None:
            if self._row_scan_gen.get(row) != gen:
                return
            try:
                item = self.project_table.item(row, 3)
                if item:
                    item.setText(scan_text_for(folder, count))
            except RuntimeError:  # dialog closed before the scan finished
                pass

        run_task(lambda: count_valid_videos_in_folder(folder), on_result=_apply)

    def _update_scanned_files_count(self, folder_str: str) -> None:
        """Debounced, asynchronous recursive scan of the selected folder (was rglob per keystroke)."""
        self._pending_scan_folder = folder_str
        if not folder_str:
            self._scan_debounce.stop()
            self._scan_gen += 1
            self.lbl_scan_info.setText("Chưa quét thư mục")
            return
        self.lbl_scan_info.setText(SCANNING_TEXT)
        self._scan_debounce.start()

    def _start_folder_scan(self) -> None:
        folder_str = self._pending_scan_folder
        self._scan_gen += 1
        gen = self._scan_gen

        def _scan() -> str:
            if not Path(folder_str).is_dir():
                return "Thư mục không tồn tại trên máy tính."
            count = count_valid_videos_in_folder(folder_str)
            if count > 0:
                return f"Đã tìm thấy: {count} video hợp lệ (quét đệ quy toàn bộ thư mục con)"
            return "Thư mục này chưa có file video hợp lệ (.mp4, .mov, .mkv, .webm, .avi)"

        def _apply(text: str) -> None:
            if gen != self._scan_gen:
                return
            try:
                self.lbl_scan_info.setText(text)
            except RuntimeError:
                pass

        def _failed(msg: str) -> None:
            if gen == self._scan_gen:
                try:
                    self.lbl_scan_info.setText(f"Lỗi khi quét thư mục: {msg}")
                except RuntimeError:
                    pass

        run_task(_scan, on_result=_apply, on_error=_failed)

    def _on_cancel_clicked(self) -> None:
        """Cooperative cancel handler terminating worker if active before rejecting."""
        if self.worker and not self.worker.is_cancelled:
            self.worker.cancel()
        self.reject()

    def _reset_ui_after_distribution(self) -> None:
        """Restores UI interactive state after background distribution finishes or errors."""
        self.btn_schedule_only.setEnabled(True)
        self.btn_run_now.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.lbl_progress_status.setVisible(False)

    def _start_async_distribution(self, auto_start: bool) -> None:
        """Dispatches multi-project folder distribution to background QThreadPool."""
        batches = self.get_selected_project_batches()
        if not batches:
            # Fallback check for single folder test compatibility
            single_folder = self.txt_folder.text().strip()
            single_pids = self.get_selected_profile_ids()
            if single_folder and Path(single_folder).is_dir() and single_pids:
                batches = [
                    {
                        "project_id": self.project_id or 1,
                        "project_name": self.project_name or "Dự Án Mục Tiêu",
                        "folder_path": single_folder,
                        "profile_ids": single_pids,
                    }
                ]
            else:
                InfoBar.warning(
                    title="Chưa có dự án hợp lệ",
                    content="Vui lòng tích chọn ít nhất 1 Dự Án có thư mục video hợp lệ và có tài khoản đích.",
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
                return

        self.auto_start_upload = auto_start
        self.btn_schedule_only.setEnabled(False)
        self.btn_run_now.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.lbl_progress_status.setVisible(True)
        self.lbl_progress_status.setText("⏳ Đang chuẩn bị quét và băm SHA-256 các nhóm đã chọn...")

        self.worker = FolderDistributionWorker(
            upload_service=self.upload_service,
            project_batches=batches,
            min_interval_hours=float(self.spin_interval.value()),
            random_order=self.chk_shuffle.isChecked(),
            deduplicate=self.chk_deduplicate.isChecked(),
            caption_template=self.txt_spintax.text().strip() or None,
            allow_comment=self.chk_comment.isChecked(),
            allow_duet=self.chk_duet.isChecked(),
            allow_stitch=self.chk_stitch.isChecked(),
            allow_hd=self.chk_allow_hd.isChecked(),
            is_ai_generated=self.chk_is_ai.isChecked(),
        )
        self.worker.signals.progress.connect(self._on_worker_progress)
        self.worker.signals.completed.connect(self._on_worker_completed)
        self.worker.signals.failed.connect(self._on_worker_failed)
        pool = QThreadPool.globalInstance()
        assert pool is not None  # exists once QApplication does
        pool.start(self.worker)

    def _on_worker_progress(self, current: int, total: int, msg: str) -> None:
        """Updates progress bar and label smoothly on main thread."""
        self.progress_bar.setMaximum(max(1, total))
        self.progress_bar.setValue(current)
        self.lbl_progress_status.setText(f"Đang phân tích ({current}/{total}): {msg}")

    def _on_worker_completed(self, items: list[dict[str, Any]]) -> None:
        """Handles successful worker completion."""
        self.distributed_videos = items
        if not self.distributed_videos:
            self._reset_ui_after_distribution()
            InfoBar.warning(
                title="Không có video khả dụng",
                content="Không tìm thấy video mới trong các thư mục hoặc toàn bộ video đã được đăng trước đó.",
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return
        self.accept()

    def _on_worker_failed(self, error_msg: str) -> None:
        """Handles worker execution failure."""
        self._reset_ui_after_distribution()
        logger.error("Error distributing multi-project folder videos asynchronously: %s", error_msg)
        InfoBar.error(
            title="Lỗi phân bổ",
            content=error_msg,
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _execute_distribution(self) -> bool:
        """Synchronous runner for headless test environments or direct execution."""
        batches = self.get_selected_project_batches()
        if not batches:
            single_folder = self.txt_folder.text().strip()
            single_pids = self.get_selected_profile_ids()
            if single_folder and Path(single_folder).is_dir() and single_pids:
                batches = [
                    {
                        "project_id": self.project_id or 1,
                        "project_name": self.project_name or "Dự Án Mục Tiêu",
                        "folder_path": single_folder,
                        "profile_ids": single_pids,
                    }
                ]
            else:
                InfoBar.warning(
                    title="Chưa chọn dự án",
                    content="Vui lòng chọn ít nhất 1 Dự Án với thư mục hợp lệ và tài khoản đích.",
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
                return False

        try:
            self.distributed_videos = self.upload_service.distribute_multi_project_batches(
                project_batches=batches,
                min_interval_hours=float(self.spin_interval.value()),
                random_order=self.chk_shuffle.isChecked(),
                deduplicate=self.chk_deduplicate.isChecked(),
                caption_template=self.txt_spintax.text().strip() or None,
                allow_comment=self.chk_comment.isChecked(),
                allow_duet=self.chk_duet.isChecked(),
                allow_stitch=self.chk_stitch.isChecked(),
                allow_hd=self.chk_allow_hd.isChecked(),
                is_ai_generated=self.chk_is_ai.isChecked(),
            )
            return len(self.distributed_videos) > 0
        except Exception as e:
            logger.error("Error distributing batches: %s", e)
            InfoBar.error(title="Lỗi phân bổ", content=str(e), position=InfoBarPosition.TOP, parent=self)
            return False

    def _on_schedule_only(self) -> None:
        self._start_async_distribution(auto_start=False)

    def _on_run_now(self) -> None:
        self._start_async_distribution(auto_start=True)
