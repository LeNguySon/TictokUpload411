"""
Add Profile Dialog for creating individual or bulk TikTok MMO profiles.
"""

from typing import Any

from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QVBoxLayout,
)
from qfluentwidgets import (
    ComboBox,
    LineEdit,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
)

from src.infrastructure.credentials.windows_vault import WindowsCredentialVault
from src.infrastructure.database.repositories.profile_repository import (
    ProfileRepository,
)
from src.infrastructure.database.repositories.project_repository import (
    ProjectRepository,
)
from src.infrastructure.database.repositories.proxy_repository import (
    ProxyRepository,
)


class AddProfileDialog(QDialog):
    """
    Dialog for adding or editing managed TikTok profiles with project and proxy associations.
    """

    def __init__(
        self,
        profile_repo: ProfileRepository,
        project_repo: ProjectRepository,
        proxy_repo: ProxyRepository,
        vault: WindowsCredentialVault | None = None,
        profile_data: dict[str, Any] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.profile_repo = profile_repo
        self.project_repo = project_repo
        self.proxy_repo = proxy_repo
        self.vault = vault or WindowsCredentialVault()
        self.profile_data = profile_data

        is_edit = bool(self.profile_data and self.profile_data.get("id"))
        self.setWindowTitle("Chỉnh Sửa Hồ Sơ TikTok" if is_edit else "Thêm Hồ Sơ TikTok Mới")
        self.resize(520, 420)
        self._init_ui()
        if is_edit:
            self._prefill_data()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        self.name_input = LineEdit(self)
        self.name_input.setPlaceholderText("Ví dụ: TikTok_US_Main_01")
        form.addRow("Tên hồ sơ:", self.name_input)

        # Project ComboBox
        self.project_combo = ComboBox(self)
        projects = self.project_repo.list_all()
        for p in projects:
            self.project_combo.addItem(p["name"], userData=p["id"])
        form.addRow("Dự án / Nhóm:", self.project_combo)

        # Proxy ComboBox
        self.proxy_combo = ComboBox(self)
        self.proxy_combo.addItem("Không dùng proxy", userData=None)
        proxies = self.proxy_repo.list_all(status="alive")
        if not proxies:
            proxies = self.proxy_repo.list_all()
        for px in proxies:
            display = f"{px['host']}:{px['port']} ({px.get('country_code', '??')})"
            self.proxy_combo.addItem(display, userData=px["id"])
        form.addRow("Proxy kết nối:", self.proxy_combo)

        # Cookies input
        self.cookie_input = PlainTextEdit(self)
        self.cookie_input.setPlaceholderText("Dán chuỗi Cookie hoặc msToken...")
        self.cookie_input.setMaximumHeight(80)
        form.addRow("Cookie / Session:", self.cookie_input)

        # OAuth Access Token (Saved to DPAPI Vault)
        self.token_input = LineEdit(self)
        self.token_input.setPlaceholderText("Access Token (Tùy chọn - Lưu vào Windows Vault)")
        form.addRow("OAuth Token:", self.token_input)

        layout.addLayout(form)

        # Bottom Buttons
        btn_layout = QHBoxLayout()
        self.btn_save = PrimaryPushButton("Lưu Hồ Sơ", self)
        self.btn_save.clicked.connect(self._on_save)
        self.btn_cancel = PushButton("Hủy", self)
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        layout.addLayout(btn_layout)

    def _prefill_data(self) -> None:
        """Prefills form inputs with existing profile data for editing."""
        if not self.profile_data:
            return
        self.btn_save.setText("Lưu Thay Đổi")
        self.name_input.setText(self.profile_data.get("name", ""))

        target_proj_id = self.profile_data.get("project_id")
        for i in range(self.project_combo.count()):
            if self.project_combo.itemData(i) == target_proj_id:
                self.project_combo.setCurrentIndex(i)
                break

        target_proxy_id = self.profile_data.get("proxy_id")
        for i in range(self.proxy_combo.count()):
            if self.proxy_combo.itemData(i) == target_proxy_id:
                self.proxy_combo.setCurrentIndex(i)
                break

        self.cookie_input.setPlainText(self.profile_data.get("cookie", "") or "")

    def _on_save(self) -> None:
        name = self.name_input.text().strip()
        if not name:
            return

        project_id = self.project_combo.currentData()
        proxy_id = self.proxy_combo.currentData()
        cookie = self.cookie_input.toPlainText().strip()
        token = self.token_input.text().strip()

        # If editing an existing profile, update database directly
        if self.profile_data and self.profile_data.get("id"):
            profile_id = self.profile_data["id"]
            update_payload: dict[str, Any] = {
                "name": name,
                "project_id": project_id,
                "proxy_id": proxy_id,
                "cookie": cookie if cookie else None,
            }
            if cookie or token:
                update_payload["status"] = "LIVE"
            self.profile_repo.update(profile_id, update_payload)

            if token:
                self.vault.save_oauth_tokens(profile_id=profile_id, access_token=token)

            self.accept()
            return

        # 1. Create real GoLogin profile with Bayesian Antidetect Fingerprint
        try:
            from src.application.services.gologin_sync_service import GoLoginSyncService

            sync_svc = GoLoginSyncService(
                profile_repo=self.profile_repo,
                project_repo=self.project_repo,
                proxy_repo=self.proxy_repo,
            )
            profile_id = sync_svc.create_real_gologin_profile(
                name=name,
                project_id=project_id,
                proxy_id=proxy_id,
                cookie=cookie if cookie else None,
            )
        except Exception:
            # Resilient fallback if daemon is unreachable
            import uuid

            profile_data = {
                "uuid": str(uuid.uuid4()),
                "name": name,
                "project_id": project_id,
                "proxy_id": proxy_id,
                "storage_dir": f"profiles/{name}",
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/152.0.0.0",
                "status": "LIVE" if cookie or token else "stopped",
                "cookie": cookie if cookie else None,
            }
            profile_id = self.profile_repo.create(profile_data)

        # AgentShield: Save access token to Windows Vault DPAPI
        if token and profile_id:
            self.vault.save_oauth_tokens(profile_id=profile_id, access_token=token)

        self.accept()
