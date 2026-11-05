"""
Profile Table Widget displaying the 28 TikTok MMO attributes with Windows 11 Fluent Design styling.
"""

from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QHeaderView, QTableWidgetItem
from qfluentwidgets import Action, FluentIcon, RoundMenu

from src.presentation.delegates.circular_avatar_delegate import CircularAvatarDelegate
from src.presentation.delegates.status_badge_delegate import StatusBadgeDelegate
from src.presentation.widgets.fast_table import FastTableWidget, RowIndex
from src.presentation.widgets.table_helpers import (
    NumericTableWidgetItem,
    format_mmo_metric,
    format_money_string,
    get_profile_table_headers,
)


def _pick(p: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """First non-empty value among ``keys``: the real `profiles` column first, then legacy aliases
    (t_follows, qg, kyc, ...) that older callers still pass."""
    for key in keys:
        value = p.get(key)
        if value is not None and value != "":
            return value
    return default


class ProfileTableWidget(FastTableWidget):
    """
    Fluent UI Table for managing TikTok profiles with 28 columns matching SSMATool parity.
    Supports multi-row context actions, crisp vector icons, and robust data persistence.
    """

    open_orbita_requested = pyqtSignal(list)
    close_orbita_requested = pyqtSignal(list)
    check_cookie_requested = pyqtSignal(list)
    sync_metrics_requested = pyqtSignal(list)
    add_video_requested = pyqtSignal(list)
    update_proxy_requested = pyqtSignal(list)
    change_project_requested = pyqtSignal(list)
    bulk_edit_requested = pyqtSignal(list)
    edit_profile_requested = pyqtSignal(int)
    open_web_profile_requested = pyqtSignal(str)
    open_folder_requested = pyqtSignal(str)
    change_status_requested = pyqtSignal(list, str)
    soft_delete_requested = pyqtSignal(list)
    remove_proxy_requested = pyqtSignal(list)
    rotate_proxy_requested = pyqtSignal(list)
    check_proxy_requested = pyqtSignal(list)
    batch_channel_update_requested = pyqtSignal(list)
    channel_radar_requested = pyqtSignal(int)
    account_health_requested = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._profile_rows = RowIndex()
        self.headers = get_profile_table_headers()
        self.setColumnCount(len(self.headers))
        self.setHorizontalHeaderLabels(self.headers)

        self.setItemDelegateForColumn(1, CircularAvatarDelegate(self))
        self.setItemDelegateForColumn(12, StatusBadgeDelegate(self))

        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setStretchLastSection(False)
        self.horizontalHeader().setFixedHeight(36)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(34)
        self.setSelectionBehavior(FastTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(FastTableWidget.SelectionMode.ExtendedSelection)
        self.setEditTriggers(FastTableWidget.EditTrigger.NoEditTriggers)
        self.setWordWrap(False)
        self.setSortingEnabled(True)
        self.setSelectRightClickedRow(True)
        self.itemSelectionChanged.connect(self.updateSelectedRows)
        self.cellDoubleClicked.connect(self._on_cell_double_clicked)

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
        self.setColumnWidth(12, 125)  # Tình trạng (Pill Badge)
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
        self.clearSelection()
        self.setUpdatesEnabled(False)
        try:
            self._profile_rows.clear()
            self.setRowCount(len(profiles))
            for row_idx, p in enumerate(profiles):
                self._populate_row(row_idx, p, stt=row_idx + 1)
        finally:
            self.setUpdatesEnabled(True)
            self.setSortingEnabled(True)

    def row_for_profile_id(self, profile_id: Any) -> int | None:
        """O(1) lookup of the current row of a profile (correct after sorting)."""
        return self._profile_rows.row(self, profile_id)

    def update_profile_row(self, row: int, profile: dict[str, Any]) -> None:
        """Re-renders a single row from an (already merged) profile dict, keeping its STT number."""
        stt_item = self.item(row, 0)
        stt = int(stt_item.text()) if stt_item and stt_item.text().isdigit() else row + 1
        sorting = self.isSortingEnabled()
        self.setSortingEnabled(False)  # setItem() with sorting on would move the row mid-update
        try:
            self._populate_row(row, profile, stt=stt)
        finally:
            self.setSortingEnabled(sorting)

    def _populate_row(self, row_idx: int, p: dict[str, Any], *, stt: int) -> None:
        """Builds all cells of one profile row (shared by full load and single-row patches)."""
        status = p.get("status", "stopped")
        cookie_raw = str(_pick(p, "cookies_browser", "cookies_json", "cookie", default="") or "")
        logged_in = bool(cookie_raw or p.get("state_loggin_browser") or p.get("logged", False))

        # Helper to create non-editable items
        def make_item(
            text: str, align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        ) -> QTableWidgetItem:
            item = QTableWidgetItem(str(text))
            item.setTextAlignment(align)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            return item

        def make_num_item(
            val: int | float | None,
            display_text: str | None = None,
            align=Qt.AlignmentFlag.AlignCenter,
        ) -> NumericTableWidgetItem:
            item = NumericTableWidgetItem(val, display_text)
            item.setTextAlignment(align)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            return item

        # Col 0: STT (holds profile record in UserRole)
        stt_item = make_num_item(stt, str(stt))
        stt_item.setData(Qt.ItemDataRole.UserRole, p)
        self.setItem(row_idx, 0, stt_item)
        self._profile_rows.add(p.get("id"), stt_item)

        # Col 1: Avt
        avt_item = make_item("👤", Qt.AlignmentFlag.AlignCenter)
        avt_path = str(p.get("avatar_path") or "")
        if avt_path:
            avt_item.setData(Qt.ItemDataRole.UserRole + 1, avt_path)
        self.setItem(row_idx, 1, avt_item)

        # Col 2: Tên hồ sơ
        self.setItem(row_idx, 2, make_item(p.get("name", "")))

        # Col 3: Logged
        logged_item = make_item("Yes" if logged_in else "No", Qt.AlignmentFlag.AlignCenter)
        logged_item.setForeground(QColor("#107C41") if logged_in else QColor("#8A8886"))
        self.setItem(row_idx, 3, logged_item)

        # Col 4: Proxy & Col 5: Type
        if p.get("vpn_config"):
            proxy_display = "🛡️ WireGuard VPN"
            proxy_type = "WireGuard"
        elif p.get("proxy_host"):
            is_rotating = p.get("proxy_type") == "rotating" or bool(p.get("change_ip_url"))
            prefix = "🔄 " if is_rotating else ""
            proxy_display = f"{prefix}{p.get('proxy_host')}"
            if p.get("proxy_port"):
                proxy_display = f"{proxy_display}:{p.get('proxy_port')}"
            proxy_type = "rotating" if is_rotating else p.get("proxy_protocol", "http")
        elif p.get("proxy_id"):
            proxy_display = f"Proxy #{p.get('proxy_id')}"
            proxy_type = p.get("proxy_protocol", "http")
        else:
            proxy_display = ""
            proxy_type = ""

        self.setItem(row_idx, 4, make_item(proxy_display))
        self.setItem(row_idx, 5, make_item(proxy_type, Qt.AlignmentFlag.AlignCenter))

        # Col 6: ID Tiktok
        self.setItem(row_idx, 6, make_item(p.get("username_on_tiktok", "")))

        # Col 7: Views(30d)
        self.setItem(
            row_idx,
            7,
            make_num_item(
                _pick(p, "views_month", "views_30d", default=0),
                format_mmo_metric(_pick(p, "views_month", "views_30d", default=0)),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            ),
        )

        # Col 8: T.Follows
        self.setItem(
            row_idx,
            8,
            make_num_item(
                _pick(p, "total_followers", "t_follows", default=0),
                format_mmo_metric(_pick(p, "total_followers", "t_follows", default=0)),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            ),
        )

        # Col 9: T.Views
        self.setItem(
            row_idx,
            9,
            make_num_item(
                _pick(p, "total_views", "t_views", default=0),
                format_mmo_metric(_pick(p, "total_views", "t_views", default=0)),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            ),
        )

        # Col 10: T.Video
        self.setItem(row_idx, 10, make_num_item(_pick(p, "total_videos", "t_video", default=0)))

        # Col 11: Email
        self.setItem(row_idx, 11, make_item(p.get("email", "")))

        # Col 12: Tình trạng (Rendered via StatusBadgeDelegate)
        status_item = make_item(status, Qt.AlignmentFlag.AlignCenter)
        status_item.setData(Qt.ItemDataRole.UserRole, status)
        status_item.setToolTip(f"Trạng thái hoạt động: {status}")
        self.setItem(row_idx, 12, status_item)

        # Col 13: Cookie (Masked)
        masked_cookie = (cookie_raw[:14] + "...") if len(cookie_raw) > 14 else cookie_raw
        self.setItem(row_idx, 13, make_item(masked_cookie))

        # Col 14: $Earned
        self.setItem(
            row_idx,
            14,
            make_num_item(
                _pick(p, "money_earned", "earned", default=0.0),
                format_money_string(_pick(p, "money_earned", "earned", default=0.0)),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            ),
        )

        # Col 15: $Balance
        self.setItem(
            row_idx,
            15,
            make_num_item(
                p.get("balance", 0.0),
                format_money_string(p.get("balance", 0.0)),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            ),
        )

        # Col 16: CS (Chỉ số sức khỏe / Account Standing & Strikes)
        strikes = int(p.get("strike_count") or 0)
        standing = str(p.get("account_standing") or "").strip()
        if strikes > 0:
            cs_display = f"🔴 {strikes}/3 Gậy"
        elif standing == "Good":
            cs_display = "🟢 Tốt"
        elif standing == "Warning":
            cs_display = "🟡 Cảnh báo"
        elif str(p.get("channel_verdict") or "").lower() == "enough":
            cs_display = "💎 Đủ Quỹ"
        else:
            cs_display = str(p.get("cs") or "—")
        self.setItem(row_idx, 16, make_item(cs_display, Qt.AlignmentFlag.AlignCenter))

        # Col 17: RPM
        self.setItem(
            row_idx,
            17,
            make_num_item(
                p.get("rpm", 0.0),
                format_money_string(p.get("rpm", 0.0)),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            ),
        )

        # Col 18: QG
        self.setItem(row_idx, 18, make_item(_pick(p, "country", "qg", default=""), Qt.AlignmentFlag.AlignCenter))

        # Col 19: KYC
        self.setItem(row_idx, 19, make_item(_pick(p, "state_kyc", "kyc", default="No"), Qt.AlignmentFlag.AlignCenter))

        # Col 20: Note
        self.setItem(row_idx, 20, make_item(_pick(p, "notes", "note", default="")))

        # Col 21: Re.Apply
        self.setItem(row_idx, 21, make_item(_pick(p, "date_reapply", "re_apply", default=""), Qt.AlignmentFlag.AlignCenter))

        # Col 22: PRIVACY
        self.setItem(row_idx, 22, make_item(p.get("privacy", "PUBLIC"), Qt.AlignmentFlag.AlignCenter))

        # Col 23: VAT
        self.setItem(row_idx, 23, make_item(p.get("vat", "No"), Qt.AlignmentFlag.AlignCenter))

        # Col 24: TS
        self.setItem(row_idx, 24, make_item(p.get("ts", "Yes"), Qt.AlignmentFlag.AlignCenter))

        # Col 25: STT (secondary)
        self.setItem(row_idx, 25, make_num_item(p.get("stt", stt)))

        # Col 26: VVP (Số lượng Video Vi Phạm)
        vvp_val = int(p.get("ttl_violations") or p.get("vvp") or 0)
        self.setItem(row_idx, 26, make_num_item(vvp_val))

        # Col 27: MP
        self.setItem(row_idx, 27, make_num_item(p.get("mp", 0)))

        # Col 28: ID
        self.setItem(row_idx, 28, make_num_item(p.get("id", 0)))

    def get_selected_profiles(self) -> list[dict[str, Any]]:
        """Returns list of selected profile dicts stored in ItemDataRole.UserRole."""
        selected_rows = sorted({index.row() for index in self.selectedIndexes()})
        profiles = []
        for row in selected_rows:
            item = self.item(row, 0)
            if item:
                data = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(data, dict):
                    profiles.append(data)
                    continue
            id_item = self.item(row, 28)
            if id_item and id_item.text().isdigit():
                profiles.append({"id": int(id_item.text())})
        return profiles

    def get_selected_profile_ids(self) -> list[int]:
        """Returns list of selected database profile IDs."""
        profiles = self.get_selected_profiles()
        return [p["id"] for p in profiles if "id" in p]

    def _on_cell_double_clicked(self, row: int, column: int) -> None:
        """Double clicking a profile row launches Orbita Browser for that profile."""
        item = self.item(row, 0)
        if item:
            data = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and "id" in data:
                self.open_orbita_requested.emit([data["id"]])
                return
        id_item = self.item(row, 28)
        if id_item and id_item.text().isdigit():
            self.open_orbita_requested.emit([int(id_item.text())])

    def mousePressEvent(self, e) -> None:
        super().mousePressEvent(e)
        if e.buttons() & Qt.MouseButton.LeftButton:
            self.updateSelectedRows()

    def mouseMoveEvent(self, e) -> None:
        super().mouseMoveEvent(e)
        if e.buttons() & Qt.MouseButton.LeftButton:
            self.updateSelectedRows()

    def keyPressEvent(self, e) -> None:
        super().keyPressEvent(e)
        if e.key() == Qt.Key.Key_Delete:
            selected_ids = self.get_selected_profile_ids()
            if selected_ids:
                self.soft_delete_requested.emit(selected_ids)

    def contextMenuEvent(self, event) -> None:
        pos = event.pos()
        item = self.itemAt(pos)
        if not item:
            return

        clicked_row = item.row()
        selected_rows = {index.row() for index in self.selectedIndexes()}
        if clicked_row not in selected_rows:
            self.clearSelection()
            self.selectRow(clicked_row)

        selected_profiles = self.get_selected_profiles()
        if not selected_profiles:
            return

        selected_ids = [p["id"] for p in selected_profiles if "id" in p]
        count = len(selected_profiles)
        first_profile = selected_profiles[0]
        first_id = first_profile.get("id")

        menu = RoundMenu(parent=self)

        # --- Root Section 1: Immediate Browser Operations ---
        orbita_title = f"Mở Trình Duyệt ({count} hồ sơ Orbita)" if count > 1 else "Mở Trình Duyệt (Orbita Antidetect)"
        act_orbita = Action(FluentIcon.GLOBE, orbita_title, self)
        act_orbita.triggered.connect(lambda: self.open_orbita_requested.emit(selected_ids))
        menu.addAction(act_orbita)

        close_title = f"Đóng Trình Duyệt ({count} hồ sơ)" if count > 1 else "Đóng Trình Duyệt"
        act_close = Action(FluentIcon.POWER_BUTTON, close_title, self)
        act_close.triggered.connect(lambda: self.close_orbita_requested.emit(selected_ids))
        menu.addAction(act_close)

        prof_label = first_profile.get("name") or f"#{first_id}"
        add_video_title = (
            f"Nạp Video Phân Bổ Cho ({count} hồ sơ)..."
            if count > 1
            else f"Nạp Video Vào Hàng Đợi Cho Hồ Sơ ({prof_label})..."
        )
        act_add_video = Action(FluentIcon.VIDEO, add_video_title, self)
        act_add_video.triggered.connect(lambda: self.add_video_requested.emit(selected_ids))
        menu.addAction(act_add_video)

        menu.addSeparator()

        # --- Submenu 1: Kênh TikTok & Sức Khỏe ---
        tiktok_menu = RoundMenu("Sức Khỏe & Kênh TikTok", self)
        tiktok_menu.setIcon(FluentIcon.HEART)

        cookie_title = f"Kiểm Tra Cookie LIVE / DIE ({count} hồ sơ)" if count > 1 else "Kiểm Tra Cookie LIVE / DIE"
        act_cookie = Action(FluentIcon.CERTIFICATE, cookie_title, self)
        act_cookie.triggered.connect(lambda: self.check_cookie_requested.emit(selected_ids))
        tiktok_menu.addAction(act_cookie)

        sync_title = f"Đồng Bộ Số Liệu TikTok ({count} hồ sơ)" if count > 1 else "Đồng Bộ Số Liệu TikTok"
        act_sync = Action(FluentIcon.SYNC, sync_title, self)
        act_sync.triggered.connect(lambda: self.sync_metrics_requested.emit(selected_ids))
        tiktok_menu.addAction(act_sync)

        act_account_health = Action(FluentIcon.HEART, "Sức Khỏe Kênh & Gậy Vi Phạm...", self)
        act_account_health.triggered.connect(lambda: self.account_health_requested.emit(int(first_id or 0)))
        tiktok_menu.addAction(act_account_health)

        act_channel_radar = Action(FluentIcon.SPEED_HIGH, "Radar Đánh Giá Kênh & Cảnh Báo...", self)
        act_channel_radar.triggered.connect(lambda: self.channel_radar_requested.emit(int(first_id or 0)))
        tiktok_menu.addAction(act_channel_radar)

        channel_title = (
            f"Cập Nhật Kênh Hàng Loạt (Avatar, Bio, Tên) ({count} hồ sơ)..."
            if count > 1
            else "Cập Nhật Kênh (Avatar, Bio, Tên)..."
        )
        act_batch_channel = Action(FluentIcon.PEOPLE, channel_title, self)
        act_batch_channel.triggered.connect(lambda: self.batch_channel_update_requested.emit(selected_ids))
        tiktok_menu.addAction(act_batch_channel)

        tiktok_user = first_profile.get("username_on_tiktok")
        act_web = Action(FluentIcon.LINK, f"Mở Trang TikTok (@{tiktok_user or 'profile'})", self)
        act_web.setEnabled(bool(tiktok_user))
        act_web.triggered.connect(lambda: self.open_web_profile_requested.emit(str(tiktok_user or "")))
        tiktok_menu.addAction(act_web)

        menu.addMenu(tiktok_menu)

        # --- Submenu 2: Quản Lý Proxy & Mạng ---
        proxy_menu = RoundMenu("Quản Lý Proxy & Mạng", self)
        proxy_menu.setIcon(FluentIcon.WIFI)

        proxy_title = f"Cập Nhật / Thêm Proxy Hàng Loạt ({count} hồ sơ)..." if count > 1 else "Cập Nhật / Gán Proxy..."
        act_proxy = Action(FluentIcon.WIFI, proxy_title, self)
        act_proxy.triggered.connect(lambda: self.update_proxy_requested.emit(selected_ids))
        proxy_menu.addAction(act_proxy)

        act_rotate_proxy = Action(FluentIcon.SYNC, "Xoay IP Proxy (Rotate IP)", self)
        act_rotate_proxy.triggered.connect(lambda: self.rotate_proxy_requested.emit(selected_ids))
        proxy_menu.addAction(act_rotate_proxy)

        act_check_proxy = Action(FluentIcon.SPEED_HIGH, "Kiểm Tra Ping / Live Proxy", self)
        act_check_proxy.triggered.connect(lambda: self.check_proxy_requested.emit(selected_ids))
        proxy_menu.addAction(act_check_proxy)

        act_remove_proxy = Action(FluentIcon.REMOVE, "Gỡ Bỏ Proxy / WireGuard VPN", self)
        act_remove_proxy.triggered.connect(lambda: self.remove_proxy_requested.emit(selected_ids))
        proxy_menu.addAction(act_remove_proxy)

        menu.addMenu(proxy_menu)

        # --- Submenu 3: Quản Lý Hồ Sơ ---
        profile_mgmt_menu = RoundMenu("Quản Lý Hồ Sơ", self)
        profile_mgmt_menu.setIcon(FluentIcon.SETTING)

        bulk_title = f"Cập Nhật Thông Tin Hàng Loạt ({count} hồ sơ)..." if count > 1 else "Chỉnh Sửa Thông Tin Hồ Sơ..."
        act_bulk = Action(FluentIcon.EDIT, bulk_title, self)
        if count > 1:
            act_bulk.triggered.connect(lambda: self.bulk_edit_requested.emit(selected_ids))
        else:
            act_bulk.triggered.connect(lambda: self.edit_profile_requested.emit(int(first_id or 0)))
        profile_mgmt_menu.addAction(act_bulk)

        project_title = f"Chuyển Vào Dự Án / Chiến Dịch ({count} hồ sơ)..." if count > 1 else "Chuyển Vào Dự Án..."
        act_project = Action(FluentIcon.FOLDER, project_title, self)
        act_project.triggered.connect(lambda: self.change_project_requested.emit(selected_ids))
        profile_mgmt_menu.addAction(act_project)

        profile_path = first_profile.get("storage_path") or first_profile.get("name", "")
        act_folder = Action(FluentIcon.FOLDER_ADD, "Mở Thư Mục Hồ Sơ (Local Profile)", self)
        act_folder.triggered.connect(lambda: self.open_folder_requested.emit(str(profile_path)))
        profile_mgmt_menu.addAction(act_folder)

        menu.addMenu(profile_mgmt_menu)

        # --- Submenu 4: Sao Chép Thông Tin ---
        copy_menu = RoundMenu("Sao Chép Thông Tin", self)
        copy_menu.setIcon(FluentIcon.COPY)

        def copy_text(val: str) -> None:
            cb = QApplication.clipboard()
            if cb:
                cb.setText(val)

        act_cp_id = Action(FluentIcon.COPY, f"Sao chép ID: {first_id}", self)
        act_cp_id.triggered.connect(lambda: copy_text(str(first_id)))
        copy_menu.addAction(act_cp_id)

        if tiktok_user:
            act_cp_user = Action(FluentIcon.COPY, f"Sao chép TikTok ID: {tiktok_user}", self)
            act_cp_user.triggered.connect(lambda: copy_text(str(tiktok_user)))
            copy_menu.addAction(act_cp_user)

        proxy_str = first_profile.get("proxy_host", "")
        if proxy_str:
            if first_profile.get("proxy_port"):
                proxy_str = f"{proxy_str}:{first_profile.get('proxy_port')}"
            act_cp_px = Action(FluentIcon.COPY, f"Sao chép Proxy: {proxy_str}", self)
            act_cp_px.triggered.connect(lambda: copy_text(str(proxy_str)))
            copy_menu.addAction(act_cp_px)

        raw_cookie = first_profile.get("cookie", "")
        if raw_cookie:
            act_cp_ck = Action(FluentIcon.COPY, "Sao chép Cookie", self)
            act_cp_ck.triggered.connect(lambda: copy_text(str(raw_cookie)))
            copy_menu.addAction(act_cp_ck)

        menu.addMenu(copy_menu)

        # --- Submenu 5: Đổi Trạng Thái ---
        status_menu = RoundMenu("Đổi Trạng Thái", self)
        status_menu.setIcon(FluentIcon.TAG)

        stat_icons = {
            "LIVE": FluentIcon.ACCEPT,
            "DIE": FluentIcon.CANCEL,
            "CHECKPOINT": FluentIcon.INFO,
            "stopped": FluentIcon.PAUSE,
        }
        for stat in ("LIVE", "DIE", "CHECKPOINT", "stopped"):
            icon = stat_icons.get(stat, FluentIcon.TAG)
            act_stat = Action(icon, stat, self)
            act_stat.triggered.connect(lambda checked, s=stat: self.change_status_requested.emit(selected_ids, s))
            status_menu.addAction(act_stat)
        menu.addMenu(status_menu)

        menu.addSeparator()

        # --- Root Bottom Section: Soft Delete ---
        delete_title = f"Chuyển Vào Thùng Rác ({count})" if count > 1 else "Chuyển Vào Thùng Rác"
        act_delete = Action(FluentIcon.DELETE, delete_title, self)
        act_delete.triggered.connect(lambda: self.soft_delete_requested.emit(selected_ids))
        menu.addAction(act_delete)

        menu.exec(event.globalPos())
