"""
Batch Folder Upload Dialog: Allows scanning video directories, multi-profile fair-share distribution,
golden hour scheduling, spintax templating, and automated batch upload triggering.
Conforms to Gloglin2609 & SamMonny UI/UX standards with Fluent UI styling.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)
from qfluentwidgets import (
    CheckBox,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    SpinBox,
)

from src.application.services.upload_service import UploadService
from src.infrastructure.database.repositories.profile_repository import ProfileRepository

logger = logging.getLogger(__name__)


class BatchFolderUploadDialog(QDialog):
    """
    Comprehensive dialog for bulk folder scanning, deduplication, Spintax captions,
    and fair-share round-robin distribution to TikTok accounts.
    """

    def __init__(
        self,
        profile_repo: ProfileRepository,
        upload_service: UploadService,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.profile_repo = profile_repo
        self.upload_service = upload_service
        self.distributed_videos: list[dict[str, Any]] = []
        self.auto_start_upload: bool = False

        self.setWindowTitle("Nạp Thư Mục & Phân Bổ Lịch Đăng Hàng Loạt (Batch Upload)")
        self.resize(760, 680)
        self._init_ui()
        self._load_profiles()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # 1. Folder Selection Group
        grp_folder = QGroupBox("1. Thư Mục Chứa Video Gốc (Source Folder)", self)
        layout_folder = QHBoxLayout(grp_folder)
        self.txt_folder = LineEdit(self)
        self.txt_folder.setPlaceholderText("Chọn hoặc dán đường dẫn thư mục chứa video...")
        self.btn_browse = PushButton("Chọn Thư Mục...", self)
        self.btn_browse.clicked.connect(self._on_browse_folder)
        layout_folder.addWidget(self.txt_folder, 1)
        layout_folder.addWidget(self.btn_browse)
        main_layout.addWidget(grp_folder)

        # 2. Target Profiles Selection Group
        grp_profiles = QGroupBox("2. Chọn Các Kênh / Tài Khoản Đăng Video (Target Profiles)", self)
        layout_profiles = QVBoxLayout(grp_profiles)
        layout_profiles.setSpacing(6)

        btn_row = QHBoxLayout()
        self.btn_select_all = PushButton("Chọn Tất Cả", self)
        self.btn_select_all.clicked.connect(self._select_all_profiles)
        self.btn_deselect_all = PushButton("Bỏ Chọn", self)
        self.btn_deselect_all.clicked.connect(self._deselect_all_profiles)
        self.lbl_selected_count = QLabel("Đã chọn: 0 tài khoản", self)
        btn_row.addWidget(self.btn_select_all)
        btn_row.addWidget(self.btn_deselect_all)
        btn_row.addStretch()
        btn_row.addWidget(self.lbl_selected_count)
        layout_profiles.addLayout(btn_row)

        self.profile_table = QTableWidget(self)
        self.profile_table.setColumnCount(4)
        self.profile_table.setHorizontalHeaderLabels(["Chọn", "ID", "Tên Kênh (Profile Name)", "Quốc Gia"])
        self.profile_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.profile_table.setColumnWidth(0, 50)
        self.profile_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.profile_table.setColumnWidth(1, 60)
        self.profile_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.profile_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.profile_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.profile_table.setFixedHeight(180)
        layout_profiles.addWidget(self.profile_table)
        main_layout.addWidget(grp_profiles)

        # 3. Distribution & Schedule Options Group
        grp_opts = QGroupBox("3. Thuật Toán Phân Bổ & Lịch Giãn Cách (Scheduling Algorithm)", self)
        layout_opts = QVBoxLayout(grp_opts)
        layout_opts.setSpacing(6)

        row1 = QHBoxLayout()
        self.chk_shuffle = CheckBox("Xáo trộn ngẫu nhiên thứ tự video (Shuffle)", self)
        self.chk_shuffle.setChecked(True)
        self.chk_deduplicate = CheckBox("Khử trùng lặp (Bỏ qua video đã nạp/đã đăng)", self)
        self.chk_deduplicate.setChecked(True)
        row1.addWidget(self.chk_shuffle)
        row1.addWidget(self.chk_deduplicate)
        row1.addStretch()
        layout_opts.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Giãn cách tối thiểu giữa các video (Giờ):", self))
        self.spin_interval = SpinBox(self)
        self.spin_interval.setRange(1, 72)
        self.spin_interval.setValue(12)
        row2.addWidget(self.spin_interval)
        row2.addSpacing(20)
        self.chk_allow_hd = CheckBox("Tải lên chất lượng cao (HD 1080p/4K)", self)
        self.chk_allow_hd.setChecked(True)
        self.chk_is_ai = CheckBox("Gắn nhãn do AI tạo ra (AI Generated)", self)
        self.chk_is_ai.setChecked(False)
        row2.addWidget(self.chk_allow_hd)
        row2.addWidget(self.chk_is_ai)
        row2.addStretch()
        layout_opts.addLayout(row2)

        # Interactions
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Tương tác video:", self))
        self.chk_comment = CheckBox("Bình luận", self)
        self.chk_comment.setChecked(True)
        self.chk_duet = CheckBox("Duet", self)
        self.chk_duet.setChecked(True)
        self.chk_stitch = CheckBox("Stitch", self)
        self.chk_stitch.setChecked(True)
        row3.addWidget(self.chk_comment)
        row3.addWidget(self.chk_duet)
        row3.addWidget(self.chk_stitch)
        row3.addStretch()
        layout_opts.addLayout(row3)

        # Spintax Caption Template
        row4 = QHBoxLayout()
        row4.addWidget(QLabel("Mẫu Tiêu Đề Spintax:", self))
        self.txt_spintax = LineEdit(self)
        self.txt_spintax.setText("{Tuyệt phẩm|Đỉnh cao|Cực phẩm} {title} #fyp #viral #trending")
        row4.addWidget(self.txt_spintax, 1)
        layout_opts.addLayout(row4)

        main_layout.addWidget(grp_opts)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_cancel = PushButton("Hủy Bỏ", self)
        btn_cancel.clicked.connect(self.reject)

        self.btn_schedule_only = PushButton("Lập Lịch Hàng Đợi (Queue Only)", self)
        self.btn_schedule_only.clicked.connect(self._on_schedule_only)

        self.btn_run_now = PrimaryPushButton("BẮT ĐẦU ĐĂNG NGAY (Run Now)", self)
        self.btn_run_now.clicked.connect(self._on_run_now)

        btn_layout.addWidget(btn_cancel)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_schedule_only)
        btn_layout.addWidget(self.btn_run_now)
        main_layout.addLayout(btn_layout)

    def _load_profiles(self) -> None:
        profiles = self.profile_repo.list_all()
        self.profile_table.setRowCount(len(profiles))
        for row, p in enumerate(profiles):
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk_item.setCheckState(Qt.CheckState.Checked)

            id_item = QTableWidgetItem(str(p["id"]))
            id_item.setFlags(Qt.ItemFlag.ItemIsEnabled)

            name_item = QTableWidgetItem(p.get("name") or p.get("account") or f"Profile #{p['id']}")
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled)

            country_item = QTableWidgetItem(p.get("country") or "US")
            country_item.setFlags(Qt.ItemFlag.ItemIsEnabled)

            self.profile_table.setItem(row, 0, chk_item)
            self.profile_table.setItem(row, 1, id_item)
            self.profile_table.setItem(row, 2, name_item)
            self.profile_table.setItem(row, 3, country_item)

        self.profile_table.itemChanged.connect(self._update_selected_count)
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

    def _on_browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Chọn Thư Mục Chứa Video", "")
        if folder:
            self.txt_folder.setText(folder)

    def _execute_distribution(self) -> bool:
        folder_str = self.txt_folder.text().strip()
        if not folder_str or not Path(folder_str).is_dir():
            InfoBar.error(
                title="Thư mục không hợp lệ",
                content="Vui lòng chọn thư mục chứa video thực tế hợp lệ.",
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return False

        selected_pids = self.get_selected_profile_ids()
        if not selected_pids:
            InfoBar.warning(
                title="Chưa chọn tài khoản",
                content="Vui lòng tích chọn ít nhất 1 tài khoản đích để phân bổ video.",
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return False

        try:
            self.distributed_videos = self.upload_service.distribute_folder_videos_to_queue(
                folder_path=folder_str,
                profile_ids=selected_pids,
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

            if not self.distributed_videos:
                InfoBar.warning(
                    title="Không có video khả dụng",
                    content="Không tìm thấy video mới trong thư mục hoặc toàn bộ video đã được đăng trước đó.",
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
                return False

            return True

        except Exception as e:
            logger.error("Error distributing folder videos: %s", e)
            InfoBar.error(
                title="Lỗi phân bổ",
                content=str(e),
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return False

    def _on_schedule_only(self) -> None:
        if self._execute_distribution():
            self.auto_start_upload = False
            self.accept()

    def _on_run_now(self) -> None:
        if self._execute_distribution():
            self.auto_start_upload = True
            self.accept()
