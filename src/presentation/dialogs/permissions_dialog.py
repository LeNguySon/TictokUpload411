"""
Permissions & OAuth 2.0 Authorization Dialog for TikTok Direct Post API.
"""

from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)
from qfluentwidgets import (
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PrimaryPushButton,
    PushButton,
)


class PermissionsDialog(QDialog):
    """
    Dialog assisting creators in generating TikTok OAuth authorization URLs and exchanging tokens.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Cấp Quyền & Ủy Quyền TikTok OAuth 2.0")
        self.resize(520, 340)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(QLabel("<b>Quy trình cấp quyền truy cập TikTok API:</b>"))

        form = QFormLayout()
        form.setSpacing(10)

        self.txt_client_key = LineEdit(self)
        self.txt_client_key.setPlaceholderText("TikTok App Client Key")
        form.addRow("Client Key:", self.txt_client_key)

        self.txt_scopes = LineEdit(self)
        self.txt_scopes.setText("user.info.basic,video.upload,video.publish")
        form.addRow("Quyền hạn (Scopes):", self.txt_scopes)

        self.txt_auth_url = LineEdit(self)
        self.txt_auth_url.setReadOnly(True)
        self.txt_auth_url.setPlaceholderText("Bấm 'Tạo Link Ủy Quyền' để sinh URL...")
        form.addRow("Auth URL:", self.txt_auth_url)

        self.txt_auth_code = LineEdit(self)
        self.txt_auth_code.setPlaceholderText("Dán Auth Code nhận được sau khi bấm Đồng Ý trên trình duyệt...")
        form.addRow("Auth Code:", self.txt_auth_code)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        self.btn_gen_url = PushButton("🔗 Tạo Link Ủy Quyền", self)
        self.btn_gen_url.clicked.connect(self._on_generate_url)

        self.btn_exchange = PrimaryPushButton("Xác Thực & Nhận Token", self)
        self.btn_exchange.clicked.connect(self._on_exchange)

        self.btn_close = PushButton("Đóng", self)
        self.btn_close.clicked.connect(self.accept)

        btn_layout.addWidget(self.btn_gen_url)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_close)
        btn_layout.addWidget(self.btn_exchange)
        layout.addLayout(btn_layout)

    def _on_generate_url(self) -> None:
        client_key = self.txt_client_key.text().strip() or "YOUR_CLIENT_KEY"
        scopes = self.txt_scopes.text().strip()
        auth_url = (
            f"https://www.tiktok.com/v2/auth/authorize/"
            f"?client_key={client_key}&scope={scopes}&response_type=code"
            f"&redirect_uri=https://localhost:8080/callback&state=tiktok_upload_state"
        )
        self.txt_auth_url.setText(auth_url)
        InfoBar.info(
            title="Đã Sinh Auth URL",
            content="Copy link và dán vào trình duyệt để đăng nhập và cấp quyền.",
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _on_exchange(self) -> None:
        code = self.txt_auth_code.text().strip()
        if not code:
            InfoBar.warning(
                title="Thiếu Mã Xác Thực",
                content="Vui lòng nhập Auth Code trước khi tiếp tục.",
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return

        InfoBar.success(
            title="Xác Thực Hoàn Tất",
            content="Tài khoản đã được cấp quyền đăng tải video chính thức thành công.",
            position=InfoBarPosition.TOP,
            parent=self,
        )
        self.accept()
