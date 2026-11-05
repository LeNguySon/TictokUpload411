"""
Batch Channel Update Dialog.
Learned from Gloglin2609/ui/views/batch_channel_update_dialog.py.

Provides a unified interface for updating Avatar, Nicknames, and Spintax Bio
across multiple selected TikTok MMO profiles with Windows 11 Fluent Design styling.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
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
    TextEdit,
)

from src.application.signals.app_signals import AppSignalBus
from src.application.workers.channel_update_worker import (
    SUPPORTED_IMAGE_EXTS,
    ChannelUpdateWorker,
)
from src.application.workers.thread_pool_manager import ThreadPoolManager
from src.domain.policies.spintax_policy import spin_text
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.presentation.dialogs.dialog_helpers import (
    STANDARD_DIALOG_MARGINS,
    STANDARD_DIALOG_SPACING,
    create_dialog_header,
)


class BatchChannelUpdateDialog(QDialog):
    """Dialog for batch updating profile avatars, nicknames, and bio with Spintax."""

    def __init__(
        self,
        selected_profile_ids: list[int],
        profile_repo: ProfileRepository | None = None,
        db_path: Path | str | None = None,
        signal_bus: AppSignalBus | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.selected_profile_ids = selected_profile_ids
        self.profile_count = len(selected_profile_ids)
        self.profile_repo = profile_repo
        self.db_path = Path(db_path) if db_path else Path("data/app.db")
        self.signal_bus = signal_bus or AppSignalBus.instance()

        self.setWindowTitle("Cập Nhật Thông Tin Kênh Hàng Loạt")
        self.resize(540, 580)
        self._init_ui()

    def exec(self) -> int:
        """Explicit Python wrapper over QDialog.exec for testability and lifecycle hooks."""
        return super().exec()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*STANDARD_DIALOG_MARGINS)
        layout.setSpacing(STANDARD_DIALOG_SPACING)

        # Header banner
        header = create_dialog_header(
            icon=FluentIcon.PEOPLE,
            title="Cập Nhật Thông Tin Kênh Hàng Loạt",
            subtitle=f"Đang áp dụng đồng loạt cho {self.profile_count} tài khoản TikTok đã chọn.",
            parent=self,
        )
        layout.addWidget(header)

        # 1. Group Avatar
        grp_avatar = QGroupBox("1. Ảnh Đại Diện (Avatar)", self)
        lay_avatar = QVBoxLayout(grp_avatar)
        self.chk_avatar = CheckBox("Kích hoạt cập nhật Avatar", grp_avatar)
        self.chk_avatar.setChecked(False)

        h_avt = QHBoxLayout()
        self.txt_avatar_path = LineEdit(grp_avatar)
        self.txt_avatar_path.setPlaceholderText("Đường dẫn file (.png, .jpg) hoặc thư mục chứa ảnh...")
        self.txt_avatar_path.setEnabled(False)
        self.btn_browse_avatar = PushButton(FluentIcon.FOLDER, "Chọn...", grp_avatar)
        self.btn_browse_avatar.setEnabled(False)
        self.btn_browse_avatar.clicked.connect(self._on_browse_avatar)
        h_avt.addWidget(self.txt_avatar_path, 1)
        h_avt.addWidget(self.btn_browse_avatar)

        self.lbl_avatar_status = QLabel("Chưa chọn nguồn ảnh avatar.", grp_avatar)
        self.lbl_avatar_status.setStyleSheet("font-size: 11px; color: #605E5C;")
        self.chk_avatar.stateChanged.connect(self._on_avatar_toggle)

        lay_avatar.addWidget(self.chk_avatar)
        lay_avatar.addLayout(h_avt)
        lay_avatar.addWidget(self.lbl_avatar_status)
        layout.addWidget(grp_avatar)

        # 2. Group Nickname
        grp_nick = QGroupBox("2. Tên Hiển Thị (Nickname)", self)
        lay_nick = QVBoxLayout(grp_nick)
        self.chk_nickname = CheckBox("Kích hoạt cập nhật Nickname", grp_nick)
        self.chk_nickname.setChecked(False)

        self.txt_nickname = LineEdit(grp_nick)
        self.txt_nickname.setPlaceholderText("Ví dụ: Kênh TikTok MMO {index}")
        self.txt_nickname.setEnabled(False)
        self.lbl_nick_hint = QLabel("Ghi chú: Dùng {index} để tự động đánh số thứ tự từ 1 đến N.", grp_nick)
        self.lbl_nick_hint.setStyleSheet("font-size: 11px; color: #605E5C;")
        self.chk_nickname.stateChanged.connect(self._on_nickname_toggle)

        lay_nick.addWidget(self.chk_nickname)
        lay_nick.addWidget(self.txt_nickname)
        lay_nick.addWidget(self.lbl_nick_hint)
        layout.addWidget(grp_nick)

        # 3. Group Bio Spintax
        grp_bio = QGroupBox("3. Tiểu Sử Kênh (Bio Spintax)", self)
        lay_bio = QVBoxLayout(grp_bio)
        self.chk_bio = CheckBox("Kích hoạt cập nhật Tiểu sử (Bio)", grp_bio)
        self.chk_bio.setChecked(False)

        self.txt_bio = TextEdit(grp_bio)
        self.txt_bio.setPlaceholderText(
            "{Xin chào|Hello} bạn đến với kênh {MMO|Viral}!\n{Follow để xem thêm|Đăng ký kênh} nhé!"
        )
        self.txt_bio.setFixedHeight(75)
        self.txt_bio.setEnabled(False)

        h_bio_btn = QHBoxLayout()
        self.btn_preview_spintax = PushButton(FluentIcon.VIEW, "Thử Nghiệm Spintax (Preview)", grp_bio)
        self.btn_preview_spintax.setEnabled(False)
        self.btn_preview_spintax.clicked.connect(self._on_preview_spintax)
        h_bio_btn.addWidget(self.btn_preview_spintax)
        h_bio_btn.addStretch()

        self.lbl_preview_bio = QLabel("Xem trước Bio Spintax: (chưa có)", grp_bio)
        self.lbl_preview_bio.setStyleSheet("font-size: 12px; color: #107C41; font-weight: 600;")
        self.chk_bio.stateChanged.connect(self._on_bio_toggle)

        lay_bio.addWidget(self.chk_bio)
        lay_bio.addWidget(self.txt_bio)
        lay_bio.addLayout(h_bio_btn)
        lay_bio.addWidget(self.lbl_preview_bio)
        layout.addWidget(grp_bio)

        # Progress
        self.progress_bar = ProgressBar(self)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Footer Buttons
        h_footer = QHBoxLayout()
        h_footer.addStretch()
        self.btn_start = PrimaryPushButton(FluentIcon.ACCEPT, "Bắt Đầu Cập Nhật", self)
        self.btn_start.clicked.connect(self._on_start_update)
        self.btn_cancel = PushButton("Đóng", self)
        self.btn_cancel.clicked.connect(self.reject)
        h_footer.addWidget(self.btn_start)
        h_footer.addWidget(self.btn_cancel)
        layout.addLayout(h_footer)

    def _on_avatar_toggle(self, state: int) -> None:
        checked = bool(state == Qt.CheckState.Checked.value or state == 2)
        self.txt_avatar_path.setEnabled(checked)
        self.btn_browse_avatar.setEnabled(checked)

    def _on_nickname_toggle(self, state: int) -> None:
        checked = bool(state == Qt.CheckState.Checked.value or state == 2)
        self.txt_nickname.setEnabled(checked)

    def _on_bio_toggle(self, state: int) -> None:
        checked = bool(state == Qt.CheckState.Checked.value or state == 2)
        self.txt_bio.setEnabled(checked)
        self.btn_preview_spintax.setEnabled(checked)

    def _on_browse_avatar(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Chọn Thư Mục Chứa Ảnh Avatar")
        if folder:
            p = Path(folder)
            count = len([f for f in p.iterdir() if f.is_file() and f.suffix.lower() in SUPPORTED_IMAGE_EXTS])
            self.txt_avatar_path.setText(folder)
            self.lbl_avatar_status.setText(f"Đã tìm thấy {count} ảnh hợp lệ trong thư mục.")
        else:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Chọn File Ảnh Avatar", "", "Image Files (*.png *.jpg *.jpeg *.webp)"
            )
            if file_path:
                self.txt_avatar_path.setText(file_path)
                self.lbl_avatar_status.setText("Đã chọn file ảnh đại diện đơn lẻ.")

    def _on_preview_spintax(self) -> None:
        template = self.txt_bio.toPlainText().strip()
        if not template:
            self.lbl_preview_bio.setText("Chưa có nội dung Spintax để thử nghiệm.")
            return
        spun = spin_text(template)
        self.lbl_preview_bio.setText(f"Xem trước: {spun}")

    def _on_start_update(self) -> None:
        if not (self.chk_avatar.isChecked() or self.chk_nickname.isChecked() or self.chk_bio.isChecked()):
            InfoBar.warning(
                title="Chưa chọn mục cập nhật",
                content="Vui lòng tích chọn ít nhất một mục: Avatar, Nickname hoặc Bio.",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000,
            )
            return

        avatar_src = self.txt_avatar_path.text().strip() if self.chk_avatar.isChecked() else None
        nick_pat = self.txt_nickname.text().strip() if self.chk_nickname.isChecked() else None
        bio_tpl = self.txt_bio.toPlainText().strip() if self.chk_bio.isChecked() else None

        self.btn_start.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        worker = ChannelUpdateWorker(
            profile_ids=self.selected_profile_ids,
            db_path=self.db_path,
            avatar_source=avatar_src,
            nickname_pattern=nick_pat,
            bio_template=bio_tpl,
            signal_bus=self.signal_bus,
        )

        def on_prog(cur, tot, pct):
            self.progress_bar.setValue(int(pct))

        def on_done():
            self.progress_bar.setValue(100)
            InfoBar.success(
                title="Cập Nhật Thành Công",
                content=f"Đã hoàn thành cập nhật {self.profile_count} tài khoản.",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000,
            )
            self.btn_start.setEnabled(True)

        worker.signals.progress.connect(on_prog)
        worker.signals.finished.connect(on_done)
        ThreadPoolManager.instance().dispatch(worker)
