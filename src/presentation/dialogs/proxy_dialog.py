"""
Proxy Manager Dialog for bulk import, async health checks, and leak protection.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidgetItem,
    QVBoxLayout,
)
from qfluentwidgets import (
    InfoBar,
    InfoBarPosition,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    TableWidget,
)

from src.application.services.proxy_service import ProxyService
from src.application.signals.app_signals import AppSignalBus
from src.application.workers.proxy_check_worker import ProxyCheckWorker
from src.application.workers.thread_pool_manager import ThreadPoolManager
from src.infrastructure.database.repositories.proxy_repository import (
    ProxyRepository,
)


class ProxyManagerDialog(QDialog):
    """
    Enterprise Proxy Manager dialog supporting 5 import formats,
    multithreaded health check dispatch, and AgentShield IP leak prevention.
    """

    def __init__(
        self,
        proxy_repo: ProxyRepository,
        proxy_service: ProxyService,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.proxy_repo = proxy_repo
        self.proxy_service = proxy_service
        self.signal_bus = AppSignalBus.instance()

        self.setWindowTitle("Quản Lý Proxy Hàng Loạt & Kiểm Định Sức Khỏe")
        self.resize(850, 560)
        self._init_ui()
        self._connect_signals()
        self.refresh_proxies()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Import Text Box
        layout.addWidget(
            QLabel(
                "Nhập danh sách proxy (1 dòng / 1 proxy - Hỗ trợ cả 5 định dạng host:port, user:pass, và URL đổi IP):"
            )
        )
        self.txt_import = PlainTextEdit(self)
        self.txt_import.setPlaceholderText(
            "103.20.5.10:8080:user1:pass1:https://rotate.link\n192.168.1.1:8080\nhttp://user:pass@1.2.3.4:8080..."
        )
        self.txt_import.setMaximumHeight(100)
        layout.addWidget(self.txt_import)

        # Toolbar
        btn_layout = QHBoxLayout()
        self.btn_import = PrimaryPushButton("Nhập Hàng Loạt", self)
        self.btn_import.clicked.connect(self._on_import)

        self.btn_check_all = PushButton("Kiểm Tra Toàn Bộ Proxy (Async)", self)
        self.btn_check_all.clicked.connect(self._on_check_all)

        self.btn_delete_dead = PushButton("Xóa Proxy Chết", self)
        self.btn_delete_dead.clicked.connect(self._on_delete_dead)

        btn_layout.addWidget(self.btn_import)
        btn_layout.addWidget(self.btn_check_all)
        btn_layout.addWidget(self.btn_delete_dead)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Proxies Table
        self.table = TableWidget(self)
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            [
                "ID",
                "Host:Port",
                "Loại",
                "Giao Thức",
                "Trạng Thái",
                "Ping (ms)",
                "IP Egress",
                "Quốc Gia",
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(TableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)

        # Bottom Close
        bottom_layout = QHBoxLayout()
        self.lbl_status = QLabel("Sẵn sàng.", self)
        self.btn_close = PushButton("Đóng", self)
        self.btn_close.clicked.connect(self.accept)

        bottom_layout.addWidget(self.lbl_status)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_close)
        layout.addLayout(bottom_layout)

    def _connect_signals(self) -> None:
        self.signal_bus.proxy_checked.connect(self._on_proxy_checked)
        self.signal_bus.proxy_leak_detected.connect(self._on_proxy_leak_alert)

    def refresh_proxies(self) -> None:
        proxies = self.proxy_repo.list_all()
        self.table.setRowCount(len(proxies))

        for row_idx, p in enumerate(proxies):

            def make_item(text: str, align=Qt.AlignmentFlag.AlignCenter):
                item = QTableWidgetItem(str(text))
                item.setTextAlignment(align)
                return item

            self.table.setItem(row_idx, 0, make_item(p["id"]))
            self.table.setItem(
                row_idx,
                1,
                make_item(f"{p['host']}:{p['port']}", Qt.AlignmentFlag.AlignLeft),
            )
            self.table.setItem(row_idx, 2, make_item(p.get("proxy_type", "static")))
            self.table.setItem(row_idx, 3, make_item(p.get("protocol", "http")))

            status = p.get("status", "unchecked")
            status_item = make_item(status)
            if status == "alive":
                status_item.setForeground(QColor("#107C41"))
            elif status == "leak_detected":
                status_item.setForeground(QColor("#D83B01"))
            elif status == "dead":
                status_item.setForeground(QColor("#A80000"))
            self.table.setItem(row_idx, 4, status_item)

            lat = p.get("latency_ms", -1)
            self.table.setItem(row_idx, 5, make_item(f"{lat}ms" if lat > 0 else "-"))
            self.table.setItem(row_idx, 6, make_item(p.get("public_ip") or "-"))
            self.table.setItem(row_idx, 7, make_item(p.get("country_code") or "-"))

    def _on_import(self) -> None:
        text = self.txt_import.toPlainText().strip()
        if not text:
            return
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        imported = self.proxy_repo.bulk_import(lines)
        self.txt_import.clear()
        self.refresh_proxies()
        InfoBar.success(
            title="Nhập Proxy Hoàn Tất",
            content=f"Đã nhập thành công {imported} proxy vào cơ sở dữ liệu.",
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _on_check_all(self) -> None:
        proxies = self.proxy_repo.list_all()
        ids = [p["id"] for p in proxies]
        if not ids:
            return

        self.lbl_status.setText(f"Đang kiểm tra {len(ids)} proxy trong luồng nền...")
        worker = ProxyCheckWorker(
            proxy_ids=ids,
            proxy_service=self.proxy_service,
            signal_bus=self.signal_bus,
        )
        worker.signals.finished.connect(lambda: self.lbl_status.setText("Kiểm tra hoàn tất."))
        ThreadPoolManager.instance().dispatch(worker)

    def _on_proxy_checked(self, proxy_id: int, is_alive: bool, latency: float, status: str) -> None:
        self.refresh_proxies()

    def _on_proxy_leak_alert(self, proxy_id: int, reason: str) -> None:
        InfoBar.error(
            title="CẢNH BÁO: RÒ RỈ IP HOST!",
            content=f"Proxy #{proxy_id} bị rò rỉ IP thực của máy: {reason}",
            position=InfoBarPosition.TOP,
            duration=8000,
            parent=self,
        )

    def _on_delete_dead(self) -> None:
        deleted = self.proxy_repo.delete_dead()
        self.refresh_proxies()
        InfoBar.info(
            title="Dọn Dẹp Proxy",
            content=f"Đã xóa {deleted} proxy chết khỏi hệ thống.",
            position=InfoBarPosition.TOP,
            parent=self,
        )
