"""
Assign Proxy Dialog for updating / reassigning proxies to one or multiple profiles.
Supports assigning existing proxies or bulk pasting and sequentially allocating new proxies.
Windows 11 Fluent Design styling.
"""

from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    ComboBox,
    FluentIcon,
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
from src.infrastructure.vpn.wireguard_manager import WireGuardManager
from src.presentation.dialogs.dialog_helpers import (
    STANDARD_DIALOG_MARGINS,
    STANDARD_DIALOG_SPACING,
    create_dialog_header,
    style_tab_widget,
)


class AssignProxyDialog(QDialog):
    """
    Dialog allowing users to assign existing proxies or bulk paste new proxies
    with sequential (1:1) or round-robin allocation to selected profiles.
    """

    DIRECT_CONNECTION = -1  # combo sentinel: deliberately run without proxy (host IP)

    def __init__(
        self,
        profile_ids: list[int],
        profile_repo: ProfileRepository,
        proxy_repo: ProxyRepository,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.profile_ids = profile_ids
        self.profile_repo = profile_repo
        self.proxy_repo = proxy_repo

        self.setWindowTitle("Cập Nhật & Thêm Proxy Hàng Loạt")
        self.resize(540, 420)
        self._init_ui()
        self._populate_proxies()

    def exec(self) -> int:
        """Explicit Python wrapper over QDialog.exec for testability and lifecycle hooks."""
        return super().exec()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*STANDARD_DIALOG_MARGINS)
        layout.setSpacing(STANDARD_DIALOG_SPACING)

        count = len(self.profile_ids)
        title_text = f"Cập Nhật Proxy cho {count} hồ sơ đang chọn" if count > 1 else "Cập Nhật Proxy cho hồ sơ đã chọn"
        header = create_dialog_header(
            icon=FluentIcon.WIFI,
            title=title_text,
            subtitle="Gán proxy có sẵn, nạp proxy xoay IP hàng loạt hoặc cấu hình WireGuard VPN.",
            parent=self,
        )
        layout.addWidget(header)

        # Tab Widget for Mode selection
        self.tabs = style_tab_widget(QTabWidget(self))

        # --- Tab 1: Existing Proxies ---
        tab_existing = QWidget()
        tab1_layout = QVBoxLayout(tab_existing)
        tab1_layout.setSpacing(10)
        lbl_tab1 = QLabel("Chọn 1 proxy có sẵn trong hệ thống để gán chung cho các hồ sơ đã chọn:")
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

        # --- Tab 3: WireGuard VPN Configuration ---
        tab_wireguard = QWidget()
        tab3_layout = QVBoxLayout(tab_wireguard)
        tab3_layout.setSpacing(8)
        lbl_tab3 = QLabel(
            "Cấu hình WireGuard VPN (.conf) riêng biệt cho hồ sơ:\n"
            "Hệ thống sẽ định tuyến lưu lượng trình duyệt độc lập qua Userspace VPN Bridge."
        )
        lbl_tab3.setStyleSheet("color: #666666; font-size: 12px;")
        lbl_tab3.setWordWrap(True)
        tab3_layout.addWidget(lbl_tab3)

        btn_row = QHBoxLayout()
        self.btn_browse_conf = PushButton("Chọn tệp .conf...", tab_wireguard)
        self.btn_browse_conf.setIcon(FluentIcon.FOLDER)
        self.btn_browse_conf.clicked.connect(self._on_browse_wg_conf)
        btn_row.addWidget(self.btn_browse_conf)
        btn_row.addStretch()
        tab3_layout.addLayout(btn_row)

        self.txt_wireguard = PlainTextEdit(tab_wireguard)
        self.txt_wireguard.setPlaceholderText(
            "[Interface]\n"
            "PrivateKey = ...\n"
            "Address = 10.14.0.2/32\n"
            "DNS = 1.1.1.1\n\n"
            "[Peer]\n"
            "PublicKey = ...\n"
            "Endpoint = 198.51.100.25:51820\n"
            "AllowedIPs = 0.0.0.0/0\n"
        )
        tab3_layout.addWidget(self.txt_wireguard)
        self.tabs.addTab(tab_wireguard, "WireGuard VPN (.conf)")

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

    def _on_browse_wg_conf(self) -> None:
        """Opens a file picker to load a WireGuard .conf file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn tệp cấu hình WireGuard (.conf)",
            "",
            "WireGuard Config (*.conf);;Tất cả tệp (*.*)",
        )
        if file_path:
            try:
                content = Path(file_path).read_text(encoding="utf-8")
                self.txt_wireguard.setPlainText(content)
            except Exception as e:
                InfoBar.error(
                    title="Lỗi Đọc Tệp",
                    content=f"Không thể đọc tệp cấu hình: {e}",
                    position=InfoBarPosition.TOP_RIGHT,
                    parent=self,
                )

    def _populate_proxies(self) -> None:
        self.combo_proxy.clear()
        self.combo_proxy.addItem("Không dùng proxy (Gỡ bỏ proxy)", userData=None)

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

        # Last, so it is never picked by accident.
        self.combo_proxy.addItem(
            "Chạy bằng IP máy — không proxy, có chủ đích", userData=self.DIRECT_CONNECTION
        )

    def _on_apply(self) -> None:
        current_tab_idx = self.tabs.currentIndex()

        if current_tab_idx == 0:
            # Mode 1: Assign single proxy from dropdown
            chosen_proxy_id = self.combo_proxy.currentData()
            if chosen_proxy_id == self.DIRECT_CONNECTION:
                updated_count = self.profile_repo.set_direct_connection(self.profile_ids)
            else:
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
        elif current_tab_idx == 1:
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
        elif current_tab_idx == 2:
            # Mode 3: Assign WireGuard VPN configuration
            conf_text = self.txt_wireguard.toPlainText().strip()
            if not conf_text:
                InfoBar.warning(
                    title="Chưa Nhập Cấu Hình",
                    content="Vui lòng dán hoặc tải tệp cấu hình WireGuard .conf.",
                    position=InfoBarPosition.TOP_RIGHT,
                    parent=self,
                )
                return

            if not WireGuardManager.validate_conf(conf_text):
                InfoBar.error(
                    title="Cấu Hình Không Hợp Lệ",
                    content="Tệp cấu hình WireGuard thiếu PrivateKey, PublicKey hoặc Endpoint.",
                    position=InfoBarPosition.TOP_RIGHT,
                    parent=self,
                )
                return

            # Atomically update WireGuard VPN config on all selected profiles
            for p_id in self.profile_ids:
                self.profile_repo.update(p_id, {"vpn_config": conf_text})

            self.accept()
