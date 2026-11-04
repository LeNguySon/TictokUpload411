"""
Profile Table Widget displaying the 28 TikTok MMO attributes with Windows 11 Fluent Design styling.
"""

from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QHeaderView, QTableWidgetItem
from qfluentwidgets import Action, RoundMenu, TableWidget

from src.presentation.widgets.table_helpers import (
    format_mmo_metric,
    format_money_string,
    get_profile_table_headers,
)


class ProfileTableWidget(TableWidget):
    """
    Fluent UI Table for managing TikTok profiles with 28 columns matching SSMATool parity.
    """

    open_orbita_requested = pyqtSignal(int)
    check_cookie_requested = pyqtSignal(int)
    change_status_requested = pyqtSignal(int, str)
    soft_delete_requested = pyqtSignal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.headers = get_profile_table_headers()
        self.setColumnCount(len(self.headers))
        self.setHorizontalHeaderLabels(self.headers)

        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setStretchLastSection(False)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(TableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(TableWidget.SelectionMode.ExtendedSelection)
        self.setWordWrap(False)
        self.setSortingEnabled(True)

        # Optimize default column widths
        self.setColumnWidth(0, 45)  # STT
        self.setColumnWidth(1, 40)  # Avt
        self.setColumnWidth(2, 140)  # Tên hồ sơ
        self.setColumnWidth(3, 70)  # Logged
        self.setColumnWidth(4, 130)  # Proxy
        self.setColumnWidth(5, 50)  # Type
        self.setColumnWidth(6, 120)  # ID Tiktok
        self.setColumnWidth(7, 85)  # Views(30d)
        self.setColumnWidth(8, 75)  # T.Follows
        self.setColumnWidth(9, 85)  # T.Views
        self.setColumnWidth(10, 60)  # T.Video
        self.setColumnWidth(11, 140)  # Email
        self.setColumnWidth(12, 80)  # Tình trạng
        self.setColumnWidth(13, 110)  # Cookie
        self.setColumnWidth(14, 75)  # $Earned
        self.setColumnWidth(15, 75)  # $Balance
        self.setColumnWidth(16, 50)  # CS
        self.setColumnWidth(17, 60)  # RPM
        self.setColumnWidth(18, 45)  # QG
        self.setColumnWidth(19, 45)  # KYC
        self.setColumnWidth(20, 100)  # Note
        self.setColumnWidth(21, 75)  # Re.Apply
        self.setColumnWidth(22, 70)  # PRIVACY
        self.setColumnWidth(23, 45)  # VAT
        self.setColumnWidth(24, 45)  # TS
        self.setColumnWidth(25, 45)  # STT
        self.setColumnWidth(26, 45)  # VVP
        self.setColumnWidth(27, 45)  # MP
        self.setColumnWidth(28, 50)  # ID

    def load_profiles(self, profiles: list[dict[str, Any]]) -> None:
        """Populates the table with profile records."""
        self.setSortingEnabled(False)
        self.setRowCount(len(profiles))

        for row_idx, p in enumerate(profiles):
            status = p.get("status", "stopped")
            logged_in = bool(p.get("cookie") or p.get("logged", False))

            # Helper to create items
            def make_item(
                text: str, align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            ) -> QTableWidgetItem:
                item = QTableWidgetItem(str(text))
                item.setTextAlignment(align)
                return item

            # Col 0: STT
            self.setItem(row_idx, 0, make_item(str(row_idx + 1), Qt.AlignmentFlag.AlignCenter))

            # Col 1: Avt
            self.setItem(row_idx, 1, make_item("👤", Qt.AlignmentFlag.AlignCenter))

            # Col 2: Tên hồ sơ
            self.setItem(row_idx, 2, make_item(p.get("name", "")))

            # Col 3: Logged
            logged_item = make_item("Yes" if logged_in else "No", Qt.AlignmentFlag.AlignCenter)
            logged_item.setForeground(QColor("#107C41") if logged_in else QColor("#8A8886"))
            self.setItem(row_idx, 3, logged_item)

            # Col 4: Proxy
            proxy_display = p.get("proxy_host", "")
            if proxy_display and p.get("proxy_port"):
                proxy_display = f"{proxy_display}:{p.get('proxy_port')}"
            elif not proxy_display and p.get("proxy_id"):
                proxy_display = f"Proxy #{p.get('proxy_id')}"
            self.setItem(row_idx, 4, make_item(proxy_display))

            # Col 5: Type
            self.setItem(row_idx, 5, make_item(p.get("proxy_protocol", "http"), Qt.AlignmentFlag.AlignCenter))

            # Col 6: ID Tiktok
            self.setItem(row_idx, 6, make_item(p.get("username_on_tiktok", "")))

            # Col 7: Views(30d)
            self.setItem(
                row_idx,
                7,
                make_item(
                    format_mmo_metric(p.get("views_30d", 0)),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                ),
            )

            # Col 8: T.Follows
            self.setItem(
                row_idx,
                8,
                make_item(
                    format_mmo_metric(p.get("t_follows", 0)),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                ),
            )

            # Col 9: T.Views
            self.setItem(
                row_idx,
                9,
                make_item(
                    format_mmo_metric(p.get("t_views", 0)), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                ),
            )

            # Col 10: T.Video
            self.setItem(row_idx, 10, make_item(str(p.get("t_video", 0)), Qt.AlignmentFlag.AlignCenter))

            # Col 11: Email
            self.setItem(row_idx, 11, make_item(p.get("email", "")))

            # Col 12: Tình trạng
            status_item = make_item(status, Qt.AlignmentFlag.AlignCenter)
            if status == "LIVE":
                status_item.setForeground(QColor("#107C41"))
            elif status == "DIE":
                status_item.setForeground(QColor("#D83B01"))
            elif status == "CHECKPOINT":
                status_item.setForeground(QColor("#CA5010"))
            self.setItem(row_idx, 12, status_item)

            # Col 13: Cookie (Masked)
            raw_cookie = p.get("cookie", "")
            masked_cookie = (raw_cookie[:14] + "...") if len(raw_cookie) > 14 else raw_cookie
            self.setItem(row_idx, 13, make_item(masked_cookie))

            # Col 14: $Earned
            self.setItem(
                row_idx,
                14,
                make_item(
                    format_money_string(p.get("earned", 0.0)),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                ),
            )

            # Col 15: $Balance
            self.setItem(
                row_idx,
                15,
                make_item(
                    format_money_string(p.get("balance", 0.0)),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                ),
            )

            # Col 16: CS
            self.setItem(row_idx, 16, make_item(str(p.get("cs", "")), Qt.AlignmentFlag.AlignCenter))

            # Col 17: RPM
            self.setItem(
                row_idx,
                17,
                make_item(
                    format_money_string(p.get("rpm", 0.0)), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                ),
            )

            # Col 18: QG
            self.setItem(row_idx, 18, make_item(p.get("qg", ""), Qt.AlignmentFlag.AlignCenter))

            # Col 19: KYC
            self.setItem(row_idx, 19, make_item(p.get("kyc", "No"), Qt.AlignmentFlag.AlignCenter))

            # Col 20: Note
            self.setItem(row_idx, 20, make_item(p.get("note", "")))

            # Col 21: Re.Apply
            self.setItem(row_idx, 21, make_item(p.get("re_apply", ""), Qt.AlignmentFlag.AlignCenter))

            # Col 22: PRIVACY
            self.setItem(row_idx, 22, make_item(p.get("privacy", "PUBLIC"), Qt.AlignmentFlag.AlignCenter))

            # Col 23: VAT
            self.setItem(row_idx, 23, make_item(p.get("vat", "No"), Qt.AlignmentFlag.AlignCenter))

            # Col 24: TS
            self.setItem(row_idx, 24, make_item(p.get("ts", "Yes"), Qt.AlignmentFlag.AlignCenter))

            # Col 25: STT (secondary)
            self.setItem(row_idx, 25, make_item(str(p.get("stt", row_idx + 1)), Qt.AlignmentFlag.AlignCenter))

            # Col 26: VVP
            self.setItem(row_idx, 26, make_item(str(p.get("vvp", 0)), Qt.AlignmentFlag.AlignCenter))

            # Col 27: MP
            self.setItem(row_idx, 27, make_item(str(p.get("mp", 0)), Qt.AlignmentFlag.AlignCenter))

            # Col 28: ID
            self.setItem(row_idx, 28, make_item(str(p.get("id", "")), Qt.AlignmentFlag.AlignCenter))

        self.setSortingEnabled(True)

    def get_selected_profile_ids(self) -> list[int]:
        """Returns list of selected database profile IDs."""
        selected_rows = {index.row() for index in self.selectedIndexes()}
        ids = []
        for row in selected_rows:
            id_item = self.item(row, 28)
            if id_item and id_item.text().isdigit():
                ids.append(int(id_item.text()))
        return ids

    def contextMenuEvent(self, event) -> None:
        selected_ids = self.get_selected_profile_ids()
        if not selected_ids:
            return

        menu = RoundMenu(parent=self)
        first_id = selected_ids[0]

        # Action: Open Orbita Browser
        act_orbita = Action("🌐 Mở Browser (Orbita Antidetect)", self)
        act_orbita.triggered.connect(lambda: self.open_orbita_requested.emit(first_id))
        menu.addAction(act_orbita)

        # Action: Check Cookie
        act_cookie = Action("🍪 Kiểm Tra Cookie LIVE / DIE", self)
        act_cookie.triggered.connect(lambda: self.check_cookie_requested.emit(first_id))
        menu.addAction(act_cookie)

        menu.addSeparator()

        # Submenu: Change Status
        status_menu = RoundMenu("Đổi Trạng Thái", self)
        for stat in ("LIVE", "DIE", "CHECKPOINT", "stopped"):
            act_stat = Action(stat, self)
            act_stat.triggered.connect(lambda checked, s=stat: self.change_status_requested.emit(first_id, s))
            status_menu.addAction(act_stat)
        menu.addMenu(status_menu)

        menu.addSeparator()

        # Action: Soft Delete
        act_delete = Action("🗑 Chuyển Vào Thùng Rác", self)
        act_delete.triggered.connect(lambda: self.soft_delete_requested.emit(selected_ids))
        menu.addAction(act_delete)

        menu.exec(event.globalPos())
