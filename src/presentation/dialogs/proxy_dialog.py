"""
Proxy Manager Dialog for bulk import, async health checks, and leak protection.
"""

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QCloseEvent, QColor
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    Action,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    RoundMenu,
    TableWidget,
)

from src.application.services.proxy_service import ProxyService
from src.application.signals.app_signals import AppSignalBus
from src.application.workers.proxy_check_worker import ProxyCheckWorker
from src.application.workers.thread_pool_manager import ThreadPoolManager
from src.infrastructure.database.repositories.proxy_repository import (
    ProxyRepository,
)
from src.presentation.dialogs.dialog_helpers import (
    STANDARD_DIALOG_MARGINS,
    STANDARD_DIALOG_SPACING,
    create_dialog_header,
)
from src.presentation.widgets.fast_table import FastTableWidget


class ProxyManagerDialog(QDialog):
    """
    Enterprise Proxy Manager dialog supporting 5 import formats,
    multithreaded health check dispatch, and AgentShield IP leak prevention.
    """

    def __init__(
        self,
        proxy_repo: ProxyRepository,
        proxy_service: ProxyService,
        parent: QWidget | None = None,
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

    def exec(self) -> int:
        """Explicit Python wrapper over QDialog.exec for testability and lifecycle hooks."""
        return super().exec()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*STANDARD_DIALOG_MARGINS)
        layout.setSpacing(STANDARD_DIALOG_SPACING)

        header = create_dialog_header(
            icon=FluentIcon.WIFI,
            title="Quản Lý Proxy Hàng Loạt & Kiểm Định Sức Khỏe",
            subtitle="Nhập proxy đa định dạng, kiểm tra ping/live, xoay IP và phòng chống rò rỉ WebRTC.",
            parent=self,
        )
        layout.addWidget(header)

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
        self.table = FastTableWidget(self)
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
        self.table.setEditTriggers(TableWidget.EditTrigger.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)
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

            def make_item(text: str, align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignCenter) -> QTableWidgetItem:
                item = QTableWidgetItem(str(text))
                item.setTextAlignment(align)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
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
        try:
            self.refresh_proxies()
        except Exception:
            pass

    def _on_proxy_leak_alert(self, proxy_id: int, reason: str) -> None:
        try:
            InfoBar.error(
                title="CẢNH BÁO: RÒ RỈ IP HOST!",
                content=f"Proxy #{proxy_id} bị rò rỉ IP thực của máy: {reason}",
                position=InfoBarPosition.TOP,
                duration=8000,
                parent=self,
            )
        except Exception:
            pass

    def _disconnect_signals(self) -> None:
        try:
            self.signal_bus.proxy_checked.disconnect(self._on_proxy_checked)
        except Exception:
            pass
        try:
            self.signal_bus.proxy_leak_detected.disconnect(self._on_proxy_leak_alert)
        except Exception:
            pass

    def closeEvent(self, event: QCloseEvent | None) -> None:
        self._disconnect_signals()
        super().closeEvent(event)

    def reject(self) -> None:
        self._disconnect_signals()
        super().reject()

    def accept(self) -> None:
        self._disconnect_signals()
        super().accept()

    def _on_delete_dead(self) -> None:
        deleted = self.proxy_repo.delete_dead()
        self.refresh_proxies()
        InfoBar.info(
            title="Dọn Dẹp Proxy",
            content=f"Đã xóa {deleted} proxy chết khỏi hệ thống.",
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _on_table_context_menu(self, pos: QPoint) -> None:
        item = self.table.itemAt(pos)
        if not item:
            return

        clicked_row = item.row()
        selected_rows = {idx.row() for idx in self.table.selectedIndexes()}
        if clicked_row not in selected_rows:
            self.table.clearSelection()
            self.table.selectRow(clicked_row)

        selected_row_list = sorted({idx.row() for idx in self.table.selectedIndexes()})
        if not selected_row_list:
            return

        selected_ids: list[int] = []
        selected_proxies = []
        for r in selected_row_list:
            id_item = self.table.item(r, 0)
            if id_item and id_item.text().isdigit():
                pid = int(id_item.text())
                selected_ids.append(pid)
                p = self.proxy_repo.get_by_id(pid)
                if p:
                    selected_proxies.append(p)

        if not selected_ids:
            return

        count = len(selected_ids)
        first_proxy = selected_proxies[0] if selected_proxies else {}

        menu = RoundMenu(parent=self.table)

        # 1. Health check
        check_text = f"Kiểm Tra Sức Khỏe ({count} proxy đã chọn)" if count > 1 else "Kiểm Tra Sức Khỏe Proxy Này"
        act_check = Action(FluentIcon.SYNC, check_text, self)
        act_check.triggered.connect(lambda: self._check_specific_proxies(selected_ids))
        menu.addAction(act_check)

        menu.addSeparator()

        # 2. Copy proxy
        copy_menu = RoundMenu("Sao Chép Proxy", self)
        copy_menu.setIcon(FluentIcon.COPY)

        def copy_text(val: str) -> None:
            cb = QApplication.clipboard()
            if cb:
                cb.setText(val)

        host_port = f"{first_proxy.get('host')}:{first_proxy.get('port')}"
        act_cp_hp = Action(FluentIcon.COPY, f"Sao chép {host_port}", self)
        act_cp_hp.triggered.connect(lambda: copy_text(host_port))
        copy_menu.addAction(act_cp_hp)

        if first_proxy.get("username"):
            full_str = f"{host_port}:{first_proxy.get('username')}:{first_proxy.get('password') or ''}"
            act_cp_full = Action(FluentIcon.COPY, "Sao chép Host:Port:User:Pass", self)
            act_cp_full.triggered.connect(lambda: copy_text(full_str))
            copy_menu.addAction(act_cp_full)

        menu.addMenu(copy_menu)

        # 3. Rotate link
        change_ip_url = first_proxy.get("change_ip_url")
        if change_ip_url:
            act_rotate = Action(FluentIcon.GLOBE, "Kích Hoạt Xoay IP (Change IP URL)", self)
            act_rotate.triggered.connect(lambda: self._trigger_rotate_ip(str(change_ip_url)))
            menu.addAction(act_rotate)

        menu.addSeparator()

        # 4. Delete
        del_text = f"Xóa {count} Proxy Đã Chọn" if count > 1 else "Xóa Proxy Khỏi Hệ Thống"
        act_del = Action(FluentIcon.DELETE, del_text, self)
        act_del.triggered.connect(lambda: self._delete_specific_proxies(selected_ids))
        menu.addAction(act_del)

        menu.exec(self.table.mapToGlobal(pos))

    def _check_specific_proxies(self, proxy_ids: list[int]) -> None:
        if not proxy_ids:
            return
        self.lbl_status.setText(f"Đang kiểm tra {len(proxy_ids)} proxy trong luồng nền...")
        worker = ProxyCheckWorker(
            proxy_ids=proxy_ids,
            proxy_service=self.proxy_service,
            signal_bus=self.signal_bus,
        )
        worker.signals.finished.connect(lambda: self.lbl_status.setText("Kiểm tra hoàn tất."))
        ThreadPoolManager.instance().dispatch(worker)

    def _delete_specific_proxies(self, proxy_ids: list[int]) -> None:
        deleted = self.proxy_repo.delete_many(proxy_ids)
        self.refresh_proxies()
        InfoBar.info(
            title="Đã Xóa Proxy",
            content=f"Đã xóa {deleted} proxy khỏi cơ sở dữ liệu.",
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _trigger_rotate_ip(self, url: str) -> None:
        import urllib.request

        from PyQt6.QtCore import QRunnable

        class RotateRunnable(QRunnable):
            def run(self_inner) -> None:
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    urllib.request.urlopen(req, timeout=10)
                except Exception:
                    pass

        ThreadPoolManager.instance().dispatch(RotateRunnable())
        InfoBar.info(
            title="Kích Hoạt Xoay IP",
            content="Đã phát lệnh đổi IP tới endpoint nhà cung cấp.",
            position=InfoBarPosition.TOP,
            parent=self,
        )
