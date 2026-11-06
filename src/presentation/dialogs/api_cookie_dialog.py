"""
API & Cookie Manager Dialog for global TikTok Direct Post credentials and cookie import/export.
"""

from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)
from qfluentwidgets import (
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
)

from src.infrastructure.credentials.windows_vault import WindowsCredentialVault
from src.presentation.dialogs.dialog_helpers import (
    STANDARD_DIALOG_MARGINS,
    STANDARD_DIALOG_SPACING,
    create_dialog_header,
)


class ApiCookieDialog(QDialog):
    """
    Dialog for configuring Global TikTok API client parameters and inspecting stored cookie vault.
    """

    def __init__(self, vault: WindowsCredentialVault | None = None, parent=None) -> None:
        super().__init__(parent)
        self.vault = vault or WindowsCredentialVault()

        self.setWindowTitle("Cấu Hình API & Quản Lý Cookie")
        self.resize(540, 420)
        self._init_ui()

    def exec(self) -> int:
        """Explicit Python wrapper over QDialog.exec for testability and lifecycle hooks."""
        return super().exec()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*STANDARD_DIALOG_MARGINS)
        layout.setSpacing(STANDARD_DIALOG_SPACING)

        header = create_dialog_header(
            icon=FluentIcon.CERTIFICATE,
            title="Cấu Hình API & Quản Lý Cookie TikTok",
            subtitle="Cấu hình TikTok Direct Post API chính thức và lưu trữ an toàn qua Windows Vault DPAPI.",
            parent=self,
        )
        layout.addWidget(header)

        layout.addWidget(QLabel("<b>Cấu hình TikTok Direct Post API chính thức:</b>"))

        form = QFormLayout()
        form.setSpacing(10)

        self.txt_client_key = LineEdit(self)
        self.txt_client_key.setPlaceholderText("TikTok App Client Key / App ID")
        form.addRow("Client Key:", self.txt_client_key)

        self.txt_client_secret = LineEdit(self)
        self.txt_client_secret.setPlaceholderText("TikTok App Client Secret")
        form.addRow("Client Secret:", self.txt_client_secret)

        self.txt_redirect_uri = LineEdit(self)
        self.txt_redirect_uri.setText("https://localhost:8080/callback")
        form.addRow("Redirect URI:", self.txt_redirect_uri)

        layout.addLayout(form)

        layout.addWidget(QLabel("<b>Nhập Cookie / Token dự phòng (JSON / Netscape):</b>"))
        self.txt_cookies = PlainTextEdit(self)
        self.txt_cookies.setPlaceholderText(
            '[{"name": "msToken", "value": "..."}, {"name": "sessionid", "value": "..."}]'
        )
        self.txt_cookies.setMaximumHeight(110)
        layout.addWidget(self.txt_cookies)

        btn_layout = QHBoxLayout()
        self.btn_save = PrimaryPushButton(FluentIcon.SAVE, "Lưu Vào Windows Vault DPAPI", self)
        self.btn_save.clicked.connect(self._on_save)
        self.btn_close = PushButton("Đóng", self)
        self.btn_close.clicked.connect(self.accept)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_close)
        btn_layout.addWidget(self.btn_save)
        layout.addLayout(btn_layout)

    def _on_save(self) -> None:
        client_key = self.txt_client_key.text().strip()
        client_secret = self.txt_client_secret.text().strip()

        if client_key and client_secret:
            # Client key in its own field (it used to be stored as "access_token").
            self.vault.save_oauth_payload(
                "GLOBAL_API_CONFIG", {"client_key": client_key, "client_secret": client_secret}
            )

        InfoBar.success(
            title="Đã Lưu Thành Công",
            content="Cấu hình API đã được mã hóa an toàn qua Windows DPAPI.",
            position=InfoBarPosition.TOP,
            parent=self,
        )
        self.accept()
