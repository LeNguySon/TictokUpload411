"""
Bulk Add Profile Dialog supporting multi-line account import and smart line parsing.
"""

import time
from typing import Any

from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidgetItem,
    QVBoxLayout,
)
from qfluentwidgets import (
    ComboBox,
    InfoBar,
    InfoBarPosition,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    TableWidget,
)

from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository


def parse_bulk_profile_line(line: str, default_name_prefix: str = "Profile") -> dict[str, Any] | None:
    """
    Parses a single line of profile import data.
    Supported patterns:
    1. Pipe-delimited: Name|Proxy|Cookie|Email|Note
    2. Name|Cookie
    3. Raw cookie string (sessionid=... or msToken=...)
    """
    raw = line.strip()
    if not raw:
        return None

    # Case 3: Raw cookie without delimiters
    if "|" not in raw:
        if "msToken=" in raw or "sessionid=" in raw:
            auto_name = f"{default_name_prefix}_{int(time.time() * 1000) % 100000}"
            return {
                "name": auto_name,
                "proxy_raw": None,
                "cookie": raw,
                "email": None,
                "note": None,
            }
        else:
            return {
                "name": raw,
                "proxy_raw": None,
                "cookie": None,
                "email": None,
                "note": None,
            }

    tokens = [t.strip() for t in raw.split("|")]
    name = tokens[0] if tokens else f"{default_name_prefix}_{int(time.time() * 1000) % 100000}"

    if len(tokens) == 2:
        return {
            "name": name,
            "proxy_raw": None,
            "cookie": tokens[1],
            "email": None,
            "note": None,
        }

    proxy_raw = tokens[1] if len(tokens) > 1 and tokens[1] else None
    cookie = tokens[2] if len(tokens) > 2 and tokens[2] else None
    email = tokens[3] if len(tokens) > 3 and tokens[3] else None
    note = tokens[4] if len(tokens) > 4 and tokens[4] else None

    return {
        "name": name,
        "proxy_raw": proxy_raw,
        "cookie": cookie,
        "email": email,
        "note": note,
    }


class BulkAddProfileDialog(QDialog):
    """
    Dialog for batch importing TikTok MMO accounts with auto-project and proxy matching.
    """

    def __init__(
        self,
        profile_repo: ProfileRepository,
        project_repo: ProjectRepository,
        proxy_repo: ProxyRepository,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.profile_repo = profile_repo
        self.project_repo = project_repo
        self.proxy_repo = proxy_repo

        self.setWindowTitle("Thêm Hàng Loạt Hồ Sơ TikTok")
        self.resize(750, 520)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Instructions & Project Choice
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Dự án đích:"))
        self.combo_project = ComboBox(self)
        projects = self.project_repo.list_all()
        for p in projects:
            self.combo_project.addItem(p["name"], userData=p["id"])
        top_layout.addWidget(self.combo_project, 1)
        layout.addLayout(top_layout)

        layout.addWidget(
            QLabel("Nhập danh sách tài khoản (1 dòng / 1 profile):\nĐịnh dạng: Tên|Proxy|Cookie|Email|Ghi chú")
        )

        self.txt_input = PlainTextEdit(self)
        self.txt_input.setPlaceholderText(
            "TikTok_US_01|103.20.5.10:8080:u1:p1|msToken=xyz; sessionid=abc|mike@gmail.com|Team US\n"
            "TikTok_US_02||msToken=123; sessionid=456||Team US\n"
            "msToken=cookie_only_auto_name..."
        )
        self.txt_input.setMinimumHeight(180)
        layout.addWidget(self.txt_input)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_preview = PushButton("Xem trước", self)
        self.btn_preview.clicked.connect(self._on_preview)

        self.btn_import = PrimaryPushButton("Nhập Tất Cả Vào Hệ Thống", self)
        self.btn_import.clicked.connect(self._on_import_all)

        self.btn_close = PushButton("Đóng", self)
        self.btn_close.clicked.connect(self.reject)

        btn_layout.addWidget(self.btn_preview)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_close)
        btn_layout.addWidget(self.btn_import)
        layout.addLayout(btn_layout)

        # Preview Table
        self.table_preview = TableWidget(self)
        self.table_preview.setColumnCount(5)
        self.table_preview.setHorizontalHeaderLabels(["Tên hồ sơ", "Proxy", "Cookie", "Email", "Ghi chú"])
        self.table_preview.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_preview.horizontalHeader().setStretchLastSection(True)
        self.table_preview.verticalHeader().setVisible(False)
        layout.addWidget(self.table_preview)

    def _get_parsed_rows(self) -> list[dict[str, Any]]:
        text = self.txt_input.toPlainText().strip()
        if not text:
            return []
        rows = []
        for line in text.splitlines():
            parsed = parse_bulk_profile_line(line)
            if parsed:
                rows.append(parsed)
        return rows

    def _on_preview(self) -> None:
        rows = self._get_parsed_rows()
        self.table_preview.setRowCount(len(rows))
        for idx, r in enumerate(rows):
            self.table_preview.setItem(idx, 0, QTableWidgetItem(r["name"]))
            self.table_preview.setItem(idx, 1, QTableWidgetItem(r["proxy_raw"] or "-"))
            masked_cookie = (
                (r["cookie"][:15] + "...") if r["cookie"] and len(r["cookie"]) > 15 else (r["cookie"] or "-")
            )
            self.table_preview.setItem(idx, 2, QTableWidgetItem(masked_cookie))
            self.table_preview.setItem(idx, 3, QTableWidgetItem(r["email"] or "-"))
            self.table_preview.setItem(idx, 4, QTableWidgetItem(r["note"] or "-"))

    def _on_import_all(self) -> None:
        rows = self._get_parsed_rows()
        if not rows:
            return

        target_project_id = self.combo_project.currentData()
        created_count = 0

        from src.application.services.gologin_sync_service import GoLoginSyncService

        sync_svc = GoLoginSyncService(
            profile_repo=self.profile_repo,
            project_repo=self.project_repo,
            proxy_repo=self.proxy_repo,
        )

        for r in rows:
            # If proxy_raw provided, register or match proxy
            proxy_id = None
            if r["proxy_raw"]:
                self.proxy_repo.bulk_import([r["proxy_raw"]])
                all_px = self.proxy_repo.list_all()
                if all_px:
                    proxy_id = all_px[-1]["id"]

            try:
                sync_svc.create_real_gologin_profile(
                    name=r["name"],
                    project_id=target_project_id,
                    proxy_id=proxy_id,
                    cookie=r["cookie"],
                )
            except Exception:
                import uuid

                profile_data = {
                    "uuid": str(uuid.uuid4()),
                    "name": r["name"],
                    "project_id": target_project_id,
                    "proxy_id": proxy_id,
                    "storage_dir": f"profiles/{r['name']}",
                    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/152.0.0.0",
                    "status": "LIVE" if r["cookie"] else "stopped",
                    "cookie": r["cookie"],
                    "email": r["email"],
                    "note": r["note"],
                }
                self.profile_repo.create(profile_data)

            created_count += 1

        InfoBar.success(
            title="Nhập Thành Công",
            content=f"Đã tạo {created_count} hồ sơ vào chiến dịch.",
            position=InfoBarPosition.TOP,
            parent=self,
        )
        self.accept()
