"""License activation dialog: shows the machine code, accepts a key, explains why access is locked."""

from __future__ import annotations

import time

from PyQt6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon, LineEdit, PlainTextEdit, PrimaryPushButton, PushButton

from src.application.services.license_service import LicenseService
from src.domain.licensing.claims import LicenseState, LicenseStatus
from src.domain.licensing.plans import PLAN_DISPLAY_NAMES
from src.presentation.dialogs.dialog_helpers import (
    STANDARD_DIALOG_MARGINS,
    STANDARD_DIALOG_SPACING,
    create_dialog_header,
)

_ERROR_COLOR = "#C42B1C"
_OK_COLOR = "#0F7B0F"


def _date(epoch: int) -> str:
    return time.strftime("%d-%m-%Y", time.localtime(epoch))


class LicenseActivationDialog(QDialog):
    def __init__(self, service: LicenseService, state: LicenseState | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.setWindowTitle("Kích hoạt bản quyền")
        self.resize(560, 420)
        self._init_ui()
        self._show_state(state or service.state)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*STANDARD_DIALOG_MARGINS)
        layout.setSpacing(STANDARD_DIALOG_SPACING)
        layout.addWidget(
            create_dialog_header(
                icon=FluentIcon.CERTIFICATE,
                title="Kích hoạt bản quyền",
                subtitle="Gửi mã máy cho nhà cung cấp để nhận key, rồi dán key vào ô bên dưới.",
                parent=self,
            )
        )

        self.lbl_status = QLabel(self)
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

        layout.addWidget(QLabel("<b>Mã máy của bạn:</b>", self))
        row = QHBoxLayout()
        self.txt_machine_code = LineEdit(self)
        self.txt_machine_code.setReadOnly(True)
        self.txt_machine_code.setText(self.service.machine_code())
        row.addWidget(self.txt_machine_code)
        self.btn_copy = PushButton(FluentIcon.COPY, "Sao chép", self)
        self.btn_copy.clicked.connect(self._on_copy)
        row.addWidget(self.btn_copy)
        layout.addLayout(row)

        layout.addWidget(QLabel("<b>Key bản quyền:</b>", self))
        self.txt_key = PlainTextEdit(self)
        self.txt_key.setPlaceholderText("TAVM1....")
        layout.addWidget(self.txt_key, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.btn_exit = PushButton("Thoát", self)
        self.btn_exit.clicked.connect(self.reject)
        buttons.addWidget(self.btn_exit)
        self.btn_activate = PrimaryPushButton(FluentIcon.ACCEPT, "Kích hoạt", self)
        self.btn_activate.clicked.connect(self._on_activate)
        buttons.addWidget(self.btn_activate)
        layout.addLayout(buttons)

    def _show_state(self, state: LicenseState) -> None:
        message = state.message
        if state.status is LicenseStatus.EXPIRED and state.claims is not None:
            message = f"Bản quyền đã hết hạn ngày {_date(state.claims.exp)}. Hãy gia hạn để tiếp tục sử dụng."
        if state.ok and state.claims is not None:
            message = (
                f"Đang dùng {PLAN_DISPLAY_NAMES[state.claims.plan]} — hạn đến {_date(state.claims.exp)}. "
                "Có thể dán key mới để gia hạn / nâng cấp."
            )
        color = _OK_COLOR if state.ok else _ERROR_COLOR
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: 600;")
        self.lbl_status.setText(message)

    def _on_copy(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.txt_machine_code.text())

    def _on_activate(self) -> None:
        key = self.txt_key.toPlainText().strip()
        if not key:
            self._show_state(LicenseState(LicenseStatus.MALFORMED))
            return
        state = self.service.activate(key)
        self._show_state(state)
        if state.ok:
            self.accept()
