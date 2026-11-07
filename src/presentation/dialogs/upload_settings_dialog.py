"""Cài Đặt Upload: the user chooses how videos are uploaded to TikTok."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PyQt6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import ComboBox, FluentIcon, PrimaryPushButton, PushButton, SwitchButton

from src.application.settings.upload_settings import (
    METHOD_LABELS,
    UploadMethod,
    UploadSettings,
    load_upload_settings,
    save_upload_settings,
)
from src.presentation.dialogs.dialog_cache import ReusableDialogMixin
from src.presentation.dialogs.dialog_helpers import (
    STANDARD_DIALOG_MARGINS,
    STANDARD_DIALOG_SPACING,
    create_dialog_header,
)

METHOD_HELP: dict[UploadMethod, str] = {
    UploadMethod.AUTO: (
        "Hồ sơ đã kết nối TikTok API (OAuth) dùng API chính thức. Hồ sơ chưa kết nối dùng trình duyệt TikTok "
        "Studio, chỉ cho video công khai; video riêng tư cần kết nối API. Lịch đăng: app tự đăng đúng giờ."
    ),
    UploadMethod.OFFICIAL: (
        "Ổn định và chính thống nhất, cần OAuth token cho từng hồ sơ. Không hẹn giờ trên TikTok (app tự đăng "
        "đúng giờ). Quyền riêng tư phải nằm trong các mức tài khoản được phép."
    ),
    UploadMethod.HYBRID: (
        "HOẠT ĐỘNG: Kết hợp truyền trực tiếp chunk 5MB tới ByteDance TOS CDN (tiết kiệm 95% RAM) và kích hoạt "
        "xuất bản qua V8 fetch injection trong trình duyệt Orbita. Đã kiểm chứng thực tế."
    ),
    UploadMethod.STUDIO: (
        "Thao tác trang TikTok Studio trong trình duyệt. CHỈ dùng cho video công khai, không hẹn giờ: "
        "phương pháp này không đặt được quyền riêng tư và giờ hẹn."
    ),
}


class UploadSettingsDialog(ReusableDialogMixin, QDialog):
    def __init__(
        self,
        store: Any,
        on_saved: Callable[[UploadSettings], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.on_saved = on_saved
        self.setWindowTitle("Cài Đặt Upload")
        self.resize(560, 440)
        self._init_ui()
        self._load(load_upload_settings(store))

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*STANDARD_DIALOG_MARGINS)
        layout.setSpacing(STANDARD_DIALOG_SPACING)
        layout.addWidget(
            create_dialog_header(
                icon=FluentIcon.SEND,
                title="Cài Đặt Upload",
                subtitle="Chọn phương pháp đăng video lên TikTok và cách xử lý khi phương pháp gặp lỗi.",
                parent=self,
            )
        )

        form = QFormLayout()
        form.setSpacing(12)
        self.cmb_method = ComboBox(self)
        for method in UploadMethod:
            self.cmb_method.addItem(METHOD_LABELS[method], userData=method.value)
        self.cmb_method.currentIndexChanged.connect(self._update_help)
        form.addRow("Phương pháp upload:", self.cmb_method)
        layout.addLayout(form)

        self.lbl_help = QLabel(self)
        self.lbl_help.setWordWrap(True)
        self.lbl_help.setStyleSheet("color: #605E5C;")
        layout.addWidget(self.lbl_help)

        self.sw_fallback = self._switch_row(
            layout,
            "Cho phép tự chuyển sang phương pháp khác khi phương pháp đã chọn lỗi",
            "Tắt (khuyến nghị): dừng và báo lỗi. Bật có thể làm một video bị đăng hai lần nếu lần đầu đã lên "
            "nhưng không nhận được xác nhận.",
        )
        self.sw_show_browser = self._switch_row(
            layout,
            "Hiện cửa sổ trình duyệt khi upload qua trình duyệt (Cookie API / Studio)",
            "Tắt: trình duyệt chạy ẩn.",
        )
        self.sw_reconcile = self._switch_row(
            layout,
            "API chính thức: chờ TikTok xác nhận đăng xong rồi mới đánh dấu 'Đã đăng'",
            "Tối đa khoảng 5 phút cho mỗi video; nếu TikTok báo lỗi xử lý, video được đánh dấu thất bại.",
        )

        layout.addStretch()
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.btn_cancel = PushButton("Hủy", self)
        self.btn_cancel.clicked.connect(self.reject)
        buttons.addWidget(self.btn_cancel)
        self.btn_save = PrimaryPushButton(FluentIcon.SAVE, "Lưu", self)
        self.btn_save.clicked.connect(self._on_save)
        buttons.addWidget(self.btn_save)
        layout.addLayout(buttons)

    def _switch_row(self, layout: QVBoxLayout, title: str, hint: str) -> SwitchButton:
        row = QHBoxLayout()
        text = QVBoxLayout()
        lbl = QLabel(f"<b>{title}</b>", self)
        lbl.setWordWrap(True)
        text.addWidget(lbl)
        hint_lbl = QLabel(hint, self)
        hint_lbl.setWordWrap(True)
        hint_lbl.setStyleSheet("color: #605E5C; font-size: 11px;")
        text.addWidget(hint_lbl)
        row.addLayout(text, 1)
        switch = SwitchButton(self)
        switch.setOnText("Bật")
        switch.setOffText("Tắt")
        row.addWidget(switch)
        layout.addLayout(row)
        return switch

    def prepare_reopen(self, on_saved: Callable[[UploadSettings], None] | None = None) -> None:
        """Reused by the main window (DialogCache): show the stored settings again."""
        if on_saved is not None:
            self.on_saved = on_saved
        self._load(load_upload_settings(self.store))

    def _load(self, settings: UploadSettings) -> None:
        self.cmb_method.setCurrentIndex(max(0, self.cmb_method.findData(settings.method.value)))
        self.sw_fallback.setChecked(settings.allow_fallback)
        self.sw_show_browser.setChecked(settings.studio_show_browser)
        self.sw_reconcile.setChecked(settings.reconcile_official)
        self._update_help()

    def _update_help(self, *_args: object) -> None:
        try:
            method = UploadMethod(self.cmb_method.currentData())
        except ValueError:
            method = UploadMethod.AUTO
        self.lbl_help.setText(METHOD_HELP[method])

    def current_settings(self) -> UploadSettings:
        return UploadSettings(
            method=UploadMethod(self.cmb_method.currentData() or UploadMethod.AUTO.value),
            allow_fallback=self.sw_fallback.isChecked(),
            studio_show_browser=self.sw_show_browser.isChecked(),
            reconcile_official=self.sw_reconcile.isChecked(),
        )

    def _on_save(self) -> None:
        settings = self.current_settings()
        save_upload_settings(settings, self.store)
        if self.on_saved is not None:
            self.on_saved(settings)
        self.accept()
