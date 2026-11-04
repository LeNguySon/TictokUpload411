"""
Assign Proxy Dialog for updating / reassigning proxies to one or multiple profiles.
Provides sharp Windows 11 Fluent Design styling.
"""

from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)
from qfluentwidgets import (
    ComboBox,
    FluentIcon,
    IconWidget,
    InfoBar,
    InfoBarPosition,
    PrimaryPushButton,
    PushButton,
)

from src.infrastructure.database.repositories.profile_repository import (
    ProfileRepository,
)
from src.infrastructure.database.repositories.proxy_repository import (
    ProxyRepository,
)


class AssignProxyDialog(QDialog):
    """
    Dialog allowing users to assign or remove proxies for single or batch profiles.
    """

    def __init__(
        self,
        profile_ids: list[int],
        profile_repo: ProfileRepository,
        proxy_repo: ProxyRepository,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.profile_ids = profile_ids
        self.profile_repo = profile_repo
        self.proxy_repo = proxy_repo

        self.setWindowTitle("Cập Nhật & Gán Proxy")
        self.resize(500, 240)
        self._init_ui()
        self._populate_proxies()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        # Header with vector FluentIcon
        header_layout = QHBoxLayout()
        icon_widget = IconWidget(FluentIcon.WIFI, self)
        icon_widget.setFixedSize(28, 28)
        header_layout.addWidget(icon_widget)

        count = len(self.profile_ids)
        title_text = f"Gán Proxy cho {count} hồ sơ đang chọn" if count > 1 else "Gán Proxy cho hồ sơ đã chọn"
        title_label = QLabel(title_text, self)
        title_label.setStyleSheet("font-size: 15px; font-weight: 600;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Instruction / summary
        desc_label = QLabel(
            "Chọn một proxy từ danh sách bên dưới để gán cho các tài khoản đã chọn.\n"
            "Hệ thống sẽ tự động cập nhật kết nối mạng của hồ sơ khi khởi chạy.",
            self,
        )
        desc_label.setStyleSheet("color: #666666; font-size: 12px;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # Proxy ComboBox
        self.combo_proxy = ComboBox(self)
        self.combo_proxy.setMinimumHeight(34)
        layout.addWidget(self.combo_proxy)

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

    def _populate_proxies(self) -> None:
        self.combo_proxy.clear()
        # Option 1: None / Remove Proxy
        self.combo_proxy.addItem("❌ Không dùng proxy (Gỡ bỏ proxy)", userData=None)

        # Option 2: Active & Registered Proxies
        proxies = self.proxy_repo.list_all()
        for px in proxies:
            status = px.get("status", "unknown").upper()
            host = px.get("host", "")
            port = px.get("port", "")
            p_type = px.get("proxy_type", "static")
            country = px.get("country_code", "??")
            latency = px.get("latency_ms", -1)

            ping_str = f"{latency}ms" if latency > 0 else ""
            display_text = f"[{status}] {host}:{port} ({p_type} - {country}) {ping_str}".strip()

            self.combo_proxy.addItem(display_text, userData=px["id"])

    def _on_apply(self) -> None:
        chosen_proxy_id = self.combo_proxy.currentData()
        updated_count = self.profile_repo.bulk_assign_proxy(self.profile_ids, chosen_proxy_id)

        if updated_count > 0:
            self.accept()
        else:
            InfoBar.warning(
                title="Cảnh Báo",
                content="Không có hồ sơ nào được cập nhật.",
                position=InfoBarPosition.TOP_RIGHT,
                parent=self,
            )
