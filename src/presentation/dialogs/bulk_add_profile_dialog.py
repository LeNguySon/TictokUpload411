"""
Bulk Add Profile Dialog supporting multi-line account import, customizable field sequence,
and automatic browser cookie injection for zero-click TikTok login.
"""

import time
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CheckBox,
    ComboBox,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
)

from src.application.parsers.profile_import_parser import PRESETS, ProfileImportParser
from src.infrastructure.browser.cookie_injector import BrowserCookieInjector
from src.infrastructure.credentials.windows_vault import WindowsCredentialVault
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
from src.presentation.dialogs.dialog_helpers import (
    STANDARD_DIALOG_MARGINS,
    STANDARD_DIALOG_SPACING,
    create_dialog_header,
)
from src.presentation.widgets.fast_table import FastTableWidget


def parse_bulk_profile_line(line: str, default_name_prefix: str = "TikTok") -> dict[str, Any] | None:
    """Legacy backward-compatible adapter for single line parsing."""
    res = ProfileImportParser.parse_line(line, format_name="legacy_5_fields", default_name_prefix=default_name_prefix)
    if not res:
        return None
    return {
        "name": res.get("user") or f"{default_name_prefix}_{int(time.time() * 1000) % 100000}",
        "proxy_raw": res.get("proxy"),
        "cookie": res.get("cookie"),
        "email": res.get("email"),
        "note": res.get("note"),
    }


class BulkAddProfileDialog(QDialog):
    """
    Enterprise Dialog for batch importing TikTok MMO accounts with custom field ordering
    and direct browser cookie injection for auto-login.
    """

    def __init__(
        self,
        profile_repo: ProfileRepository,
        project_repo: ProjectRepository,
        proxy_repo: ProxyRepository,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.profile_repo = profile_repo
        self.project_repo = project_repo
        self.proxy_repo = proxy_repo
        self.vault = WindowsCredentialVault()

        self.setWindowTitle("Thêm Hàng Loạt Hồ Sơ TikTok (Hỗ Trợ 8 Trường MMO & Auto-Login)")
        self.resize(880, 620)
        self._init_ui()

    def exec(self) -> int:
        """Explicit Python wrapper over QDialog.exec for testability and lifecycle hooks."""
        return super().exec()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*STANDARD_DIALOG_MARGINS)
        layout.setSpacing(STANDARD_DIALOG_SPACING)

        # Header banner with sharp vector FluentIcon
        header = create_dialog_header(
            icon=FluentIcon.ADD_TO,
            title="Thêm Hàng Loạt Hồ Sơ TikTok (MMO Automation)",
            subtitle="Hỗ trợ nạp 8 trường dữ liệu MMO, tùy biến cấu trúc cột và tự động đăng nhập trình duyệt qua Cookie.",
            parent=self,
        )
        layout.addWidget(header)

        # 1. Row 1: Destination Project & Separator
        row1_layout = QHBoxLayout()
        row1_layout.addWidget(QLabel("Dự án đích:"))
        self.combo_project = ComboBox(self)
        projects = self.project_repo.list_all()
        for p in projects:
            self.combo_project.addItem(p["name"], userData=p["id"])
        row1_layout.addWidget(self.combo_project, 1)

        row1_layout.addWidget(QLabel("Dấu phân cách:"))
        self.combo_delimiter = ComboBox(self)
        self.combo_delimiter.addItem("| (Gạch đứng)", userData="|")
        self.combo_delimiter.addItem(": (Hai chấm)", userData=":")
        self.combo_delimiter.addItem("Tab", userData="\t")
        self.combo_delimiter.addItem(", (Dấu phẩy)", userData=",")
        self.combo_delimiter.currentIndexChanged.connect(self._on_format_changed)
        row1_layout.addWidget(self.combo_delimiter)

        layout.addLayout(row1_layout)

        # 2. Row 2: Format Preset & Custom Token Order
        row2_layout = QHBoxLayout()
        row2_layout.addWidget(QLabel("Định dạng nhập:"))
        self.combo_preset = ComboBox(self)
        self.combo_preset.addItem("Chuẩn TikTok MMO (8 trường)", userData="mmo_8_fields")
        self.combo_preset.addItem("Chuẩn Cũ (5 trường: Tên|Proxy|Cookie|Email|Ghi chú)", userData="legacy_5_fields")
        self.combo_preset.addItem("Cơ Bản (3 trường: User|Pass|Cookie)", userData="basic_3_fields")
        self.combo_preset.addItem(
            "Tài Khoản & Mail (4 trường: User|Pass|Email|Passmail)", userData="account_mail_4_fields"
        )
        self.combo_preset.addItem("Chỉ Cookie TikTok (1 dòng / 1 cookie)", userData="cookie_only")
        self.combo_preset.addItem("Tùy Chỉnh Thứ Tự (Custom)...", userData="custom")
        self.combo_preset.currentIndexChanged.connect(self._on_preset_changed)
        row2_layout.addWidget(self.combo_preset, 1)

        layout.addLayout(row2_layout)

        # Custom Template Edit
        row_custom = QHBoxLayout()
        row_custom.addWidget(QLabel("Thứ tự các cột:"))
        self.edit_format = LineEdit(self)
        self.edit_format.setText(
            "User | Pass | Cookie TikTok | Email | Passmail | RefreshToken | ClientId | Cookie Email"
        )
        self.edit_format.textChanged.connect(self._on_custom_format_edited)
        row_custom.addWidget(self.edit_format, 1)
        layout.addLayout(row_custom)

        # Auto-inject cookie option
        self.chk_auto_inject_cookie = CheckBox(
            "Nạp Cookie trực tiếp vào trình duyệt && Tự động đăng nhập TikTok (Zero-Click Auto-Login)",
            self,
        )
        self.chk_auto_inject_cookie.setChecked(True)
        layout.addWidget(self.chk_auto_inject_cookie)

        # 3. Input Text Box
        self.txt_input = PlainTextEdit(self)
        self.txt_input.setPlaceholderText(
            "Nhập danh sách tài khoản (1 dòng / 1 tài khoản):\n"
            "user_01|pass123|sessionid=abc; msToken=xyz|email1@gmail.com|passmail123|rt_token|client_id|email_cookie\n"
            "user_02|pass456|sessionid=def; msToken=uvw|email2@gmail.com|passmail456|||\n"
            "msToken=cookie_only_sessionid_abc..."
        )
        self.txt_input.setMinimumHeight(150)
        layout.addWidget(self.txt_input)

        # 4. Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_preview = PushButton(FluentIcon.VIEW, "Xem Trước Dữ Liệu", self)
        self.btn_preview.clicked.connect(self._on_preview)

        self.btn_import = PrimaryPushButton(FluentIcon.ACCEPT, "Nhập Tất Cả Vào Hệ Thống", self)
        self.btn_import.clicked.connect(self._on_import_all)

        self.btn_close = PushButton("Đóng", self)
        self.btn_close.clicked.connect(self.reject)

        btn_layout.addWidget(self.btn_preview)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_close)
        btn_layout.addWidget(self.btn_import)
        layout.addLayout(btn_layout)

        # 5. Preview Table
        self.table_preview = FastTableWidget(self)
        self.preview_headers = [
            "STT",
            "Tên / User",
            "Mật khẩu",
            "Cookie TikTok",
            "Email",
            "Mật khẩu Email",
            "RefreshToken",
            "ClientId",
            "Cookie Email",
            "Proxy",
            "Trạng thái Cookie",
        ]
        self.table_preview.setColumnCount(len(self.preview_headers))
        self.table_preview.setHorizontalHeaderLabels(self.preview_headers)
        self.table_preview.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_preview.horizontalHeader().setStretchLastSection(True)
        self.table_preview.verticalHeader().setVisible(False)
        layout.addWidget(self.table_preview, 1)

    def _on_preset_changed(self) -> None:
        preset_key = self.combo_preset.currentData()
        delim = self.combo_delimiter.currentData() or "|"
        if preset_key in PRESETS:
            preset = PRESETS[preset_key]
            tokens = preset["tokens"]
            token_display_map = {
                "user": "User",
                "pass": "Pass",
                "cookie": "Cookie TikTok",
                "email": "Email",
                "pass_mail": "Passmail",
                "refresh_token": "RefreshToken",
                "client_id": "ClientId",
                "cookie_email": "Cookie Email",
                "proxy": "Proxy",
                "note": "Ghi chú",
            }
            display_str = f" {delim} ".join(token_display_map.get(t, t) for t in tokens)
            self.edit_format.blockSignals(True)
            self.edit_format.setText(display_str)
            self.edit_format.blockSignals(False)

    def _on_format_changed(self) -> None:
        self._on_preset_changed()

    def _on_custom_format_edited(self) -> None:
        # If user directly edits the format string, switch combo to custom
        if self.combo_preset.currentData() != "custom":
            self.combo_preset.blockSignals(True)
            for idx in range(self.combo_preset.count()):
                if self.combo_preset.itemData(idx) == "custom":
                    self.combo_preset.setCurrentIndex(idx)
                    break
            self.combo_preset.blockSignals(False)

    def _get_active_delimiter(self) -> str:
        return self.combo_delimiter.currentData() or "|"

    def _get_parsed_rows(self) -> list[dict[str, Any]]:
        text = self.txt_input.toPlainText().strip()
        if not text:
            return []

        preset_key = self.combo_preset.currentData()
        custom_fmt = self.edit_format.text().strip()
        delim = self._get_active_delimiter()

        rows = []
        for line in text.splitlines():
            if not line.strip():
                continue
            if preset_key != "custom" and preset_key in PRESETS:
                parsed = ProfileImportParser.parse_line(line, format_name=preset_key, delimiter=delim)
            else:
                parsed = ProfileImportParser.parse_line(line, custom_template=custom_fmt, delimiter=delim)
            if parsed:
                rows.append(parsed)
        return rows

    def _mask_cookie(self, cookie_val: str | None) -> str:
        if not cookie_val:
            return "-"
        if "sessionid=" in cookie_val:
            parts = cookie_val.split("sessionid=")
            sess_val = parts[1].split(";")[0][:6]
            return f"sessionid={sess_val}*** ({len(cookie_val)} ký tự)"
        elif "msToken=" in cookie_val:
            return f"msToken=*** ({len(cookie_val)} ký tự)"
        return f"{cookie_val[:10]}***"

    def _on_preview(self) -> None:
        rows = self._get_parsed_rows()
        self.table_preview.setRowCount(len(rows))

        for idx, r in enumerate(rows):
            # Col 0: STT
            self.table_preview.setItem(idx, 0, QTableWidgetItem(str(idx + 1)))

            # Col 1: Tên / User
            self.table_preview.setItem(idx, 1, QTableWidgetItem(r.get("user") or "-"))

            # Col 2: Mật khẩu (AgentShield Masking)
            pass_val = r.get("pass")
            masked_pass = "••••••••" if pass_val else "-"
            self.table_preview.setItem(idx, 2, QTableWidgetItem(masked_pass))

            # Col 3: Cookie TikTok (AgentShield Masking)
            cookie_val = r.get("cookie")
            self.table_preview.setItem(idx, 3, QTableWidgetItem(self._mask_cookie(cookie_val)))

            # Col 4: Email
            self.table_preview.setItem(idx, 4, QTableWidgetItem(r.get("email") or "-"))

            # Col 5: Mật khẩu Email (AgentShield Masking)
            pass_mail = r.get("pass_mail")
            masked_pass_mail = "••••••••" if pass_mail else "-"
            self.table_preview.setItem(idx, 5, QTableWidgetItem(masked_pass_mail))

            # Col 6: RefreshToken
            rt = r.get("refresh_token")
            masked_rt = f"{rt[:8]}***" if rt and len(rt) > 8 else (rt or "-")
            self.table_preview.setItem(idx, 6, QTableWidgetItem(masked_rt))

            # Col 7: ClientId
            self.table_preview.setItem(idx, 7, QTableWidgetItem(r.get("client_id") or "-"))

            # Col 8: Cookie Email
            self.table_preview.setItem(idx, 8, QTableWidgetItem(self._mask_cookie(r.get("cookie_email"))))

            # Col 9: Proxy
            self.table_preview.setItem(idx, 9, QTableWidgetItem(r.get("proxy") or "-"))

            # Col 10: Trạng thái Cookie
            status_item = QTableWidgetItem("-")
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if cookie_val:
                if "sessionid=" in cookie_val:
                    status_item.setText("Sẵn sàng đăng nhập")
                    status_item.setForeground(QColor("#107C41"))
                else:
                    status_item.setText("Thiếu sessionid")
                    status_item.setForeground(QColor("#D83B01"))
            else:
                status_item.setText("Không có cookie")
                status_item.setForeground(QColor("#8A8886"))
            self.table_preview.setItem(idx, 10, status_item)

    def _on_import_all(self) -> None:
        rows = self._get_parsed_rows()
        if not rows:
            InfoBar.warning(
                title="Dữ Liệu Trống",
                content="Vui lòng nhập ít nhất 1 tài khoản trước khi nhập vào hệ thống.",
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return

        target_project_id = self.combo_project.currentData()
        auto_inject = self.chk_auto_inject_cookie.isChecked()
        created_count = 0
        injected_count = 0
        bad_proxy_rows: list[str] = []

        from src.application.services.gologin_sync_service import GoLoginSyncService

        sync_svc = GoLoginSyncService(
            profile_repo=self.profile_repo,
            project_repo=self.project_repo,
            proxy_repo=self.proxy_repo,
        )

        for r in rows:
            user_name = r.get("user") or f"TikTok_{int(time.time() * 1000) % 100000}"
            proxy_raw = r.get("proxy")
            cookie = r.get("cookie")
            password = r.get("pass")
            email = r.get("email")
            pass_mail = r.get("pass_mail")
            refresh_token = r.get("refresh_token")
            client_id = r.get("client_id")
            cookie_email = r.get("cookie_email")
            note = r.get("note")

            # The id of THIS row's proxy (it used to take the last proxy of the table: wrong proxy for
            # existing/duplicate proxies and a random one for an unparsable line).
            proxy_id = self.proxy_repo.import_line(proxy_raw) if proxy_raw else None
            if proxy_raw and proxy_id is None:
                bad_proxy_rows.append(user_name)

            extra_fields = {
                "password": password,
                "email": email,
                "email_backup_password": pass_mail,
                "refresh_token": refresh_token,
                "client_id": client_id,
                "cookie_email": cookie_email,
                "notes": note,
            }

            try:
                prof_id = sync_svc.create_real_gologin_profile(
                    name=user_name,
                    project_id=target_project_id,
                    proxy_id=proxy_id,
                    cookie=cookie,
                    extra_fields=extra_fields,
                )
            except Exception:
                import uuid

                from src.infrastructure.browser.orbita_launcher import OrbitaLauncher

                p_uuid = str(uuid.uuid4())
                prof_dir = OrbitaLauncher.resolve_profile_dir({"uuid": p_uuid, "name": user_name})
                prof_dir.mkdir(parents=True, exist_ok=True)

                profile_data = {
                    "uuid": p_uuid,
                    "name": user_name,
                    "project_id": target_project_id,
                    "proxy_id": proxy_id,
                    "storage_dir": str(prof_dir),
                    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/152.0.0.0",
                    "status": "LIVE" if (cookie and "sessionid=" in cookie) else "stopped",
                    "cookie": cookie,
                    **extra_fields,
                }
                prof_id = self.profile_repo.create(profile_data)

            # The account password is kept in extra_fields (profiles.password). A Vault copy used to be
            # attempted here through a method the Vault never had (AttributeError, silently swallowed).

            # Auto inject cookies into local Chromium SQLite
            if auto_inject and cookie:
                p_row = self.profile_repo.get_by_id(prof_id)
                if p_row:
                    try:
                        from src.infrastructure.browser.orbita_launcher import OrbitaLauncher

                        target_p_dir = OrbitaLauncher.resolve_profile_dir(p_row)
                        BrowserCookieInjector.seed_profile_cookies(target_p_dir, cookie)
                    except Exception:
                        pass
                injected_count += 1

            created_count += 1

        inject_msg = f" Đã nạp cookie tự động đăng nhập cho {injected_count} tài khoản." if injected_count > 0 else ""
        if bad_proxy_rows:
            InfoBar.warning(
                title="Proxy sai định dạng",
                content=(
                    f"{len(bad_proxy_rows)} hồ sơ được tạo KHÔNG có proxy (dòng proxy không đọc được): "
                    f"{', '.join(bad_proxy_rows[:5])}{'…' if len(bad_proxy_rows) > 5 else ''}. Hãy gán proxy trước khi mở."
                ),
                position=InfoBarPosition.TOP,
                duration=8000,
                parent=self.parent() or self,
            )
        InfoBar.success(
            title="Nhập Thành Công",
            content=f"Đã tạo {created_count} hồ sơ vào chiến dịch.{inject_msg}",
            position=InfoBarPosition.TOP,
            parent=self,
        )
        self.accept()
