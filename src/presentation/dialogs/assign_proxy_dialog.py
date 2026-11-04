"""
Assign Proxy Dialog for updating / reassigning proxies to one or multiple profiles.
Supports assigning existing proxies or bulk pasting and sequentially allocating new proxies.
Windows 11 Fluent Design styling.
"""

from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    ComboBox,
    FluentIcon,
    IconWidget,
    InfoBar,
    InfoBarPosition,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
)

from src.infrastructure.database.repositories.profile_repository import (
    ProfileRepository,
)
from src.infrastructure.database.repositories.proxy_repository import (
    ProxyRepository,
    parse_proxy_line,
)


class AssignProxyDialog(QDialog):
    """
    Dialog allowing users to assign existing proxies or bulk paste new proxies
    with sequential (1:1) or round-robin allocation to selected profiles.
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

        self.setWindowTitle("Cập Nhật & Thêm Proxy Hàng Loạt")
        self.resize(540, 420)
        self._init_ui()
        self._populate_proxies()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header with vector FluentIcon
        header_layout = QHBoxLayout()
        icon_widget = IconWidget(FluentIcon.WIFI, self)
        icon_widget.setFixedSize(28, 28)
        header_layout.addWidget(icon_widget)

        count = len(self.profile_ids)
        title_text = (
            f"Cập Nhật Proxy cho {count} hồ sơ đang chọn"
            if count > 1
            else "Cập Nhật Proxy cho hồ sơ đã chọn"
        )
        title_label = QLabel(title_text, self)
        title_label.setStyleSheet("font-size: 15px; font-weight: 600;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Tab Widget for Mode selection
        self.tabs = QTabWidget(self)

        # --- Tab 1: Existing Proxies ---
        tab_existing = QWidget()
        tab1_layout = QVBoxLayout(tab_existing)
        tab1_layout.setSpacing(10)
        lbl_tab1 = QLabel(
            "Chọn 1 proxy có sẵn trong hệ thống để gán chung cho các hồ sơ đã chọn:"
        )
        lbl_tab1.setStyleSheet("color: #666666; font-size: 12px;")
        tab1_layout.addWidget(lbl_tab1)

        self.combo_proxy = ComboBox(tab_existing)
        self.combo_proxy.setMinimumHeight(34)
        tab1_layout.addWidget(self.combo_proxy)
        tab1_layout.addStretch()
        self.tabs.addTab(tab_existing, "Proxy Có Sẵn")

        # --- Tab 2: Bulk Add & Assign New Proxies ---
        tab_bulk = QWidget()
        tab2_layout = QVBoxLayout(tab_bulk)
        tab2_layout.setSpacing(8)
        lbl_tab2 = QLabel(
            "Dán danh sách Proxy mới (1 dòng / 1 proxy - Hỗ trợ host:port, user:pass, rotate url):\n"
            f"Hệ thống sẽ lưu vào CSDL và tự động gán lần lượt (1:1) cho {count} hồ sơ đã chọn."
        )
        lbl_tab2.setStyleSheet("color: #666666; font-size: 12px;")
        lbl_tab2.setWordWrap(True)
        tab2_layout.addWidget(lbl_tab2)

        self.txt_bulk_proxies = PlainTextEdit(tab_bulk)
        self.txt_bulk_proxies.setPlaceholderText(
            "103.20.5.10:8080:user1:pass1\n"
            "103.20.5.11:8080:user2:pass2:https://rotate.link\n"
            "http://user:pass@1.2.3.4:8080..."
        )
        tab2_layout.addWidget(self.txt_bulk_proxies)
        self.tabs.addTab(tab_bulk, "Thêm Mới Hàng Loạt (1:1)")

        layout.addWidget(self.tabs)

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
        self.combo_proxy.addItem("❌ Không dùng proxy (Gỡ bỏ proxy)", userData=None)

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
        current_tab_idx = self.tabs.currentIndex()

        if current_tab_idx == 0:
            # Mode 1: Assign single proxy from dropdown
            chosen_proxy_id = self.combo_proxy.currentData()
            updated_count = self.profile_repo.bulk_assign_proxy(
                self.profile_ids, chosen_proxy_id
            )
            if updated_count > 0:
                self.accept()
            else:
                InfoBar.warning(
                    title="Cảnh Báo",
                    content="Không có hồ sơ nào được cập nhật.",
                    position=InfoBarPosition.TOP_RIGHT,
                    parent=self,
                )
        else:
            # Mode 2: Bulk paste new proxies and sequentially allocate 1:1
            raw_text = self.txt_bulk_proxies.toPlainText().strip()
            if not raw_text:
                InfoBar.warning(
                    title="Chưa Nhập Proxy",
                    content="Vui lòng dán danh sách proxy vào ô văn bản.",
                    position=InfoBarPosition.TOP_RIGHT,
                    parent=self,
                )
                return

            lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
            new_proxy_ids: list[int] = []
            for line in lines:
                parsed = parse_proxy_line(line)
                if parsed:
                    host, port, user, pwd, proto, curl = parsed
                    ptype = "rotating" if curl else "static"
                    px_id = self.proxy_repo.create(
                        host=host,
                        port=port,
                        username=user,
                        password=pwd,
                        protocol=proto,
                        proxy_type=ptype,
                        change_ip_url=curl,
                    )
                    new_proxy_ids.append(px_id)

            if not new_proxy_ids:
                InfoBar.error(
                    title="Định Dạng Không Hợp Lệ",
                    content="Không nhận diện được proxy hợp lệ nào từ văn bản đã nhập.",
                    position=InfoBarPosition.TOP_RIGHT,
                    parent=self,
                )
                return

            # Allocate sequentially / round-robin
            for idx, p_id in enumerate(self.profile_ids):
                assigned_px = new_proxy_ids[idx % len(new_proxy_ids)]
                self.profile_repo.update(p_id, proxy_id=assigned_px)

            self.accept()
