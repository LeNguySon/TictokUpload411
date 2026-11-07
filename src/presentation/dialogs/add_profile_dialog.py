"""
Add Profile Dialog for creating individual or bulk TikTok MMO profiles.
"""

import logging
from typing import Any

from PyQt6 import sip
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    ComboBox,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
)

from src.application.workers.task_worker import run_task
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
from src.presentation.dialogs.dialog_helpers import (
    STANDARD_DIALOG_MARGINS,
    STANDARD_DIALOG_SPACING,
    create_dialog_header,
)

logger = logging.getLogger(__name__)


def create_profile(
    *,
    name: str,
    project_id: int | None,
    proxy_id: int | None,
    cookie: str,
    token: str,
    profile_repo: ProfileRepository,
    project_repo: ProjectRepository,
    proxy_repo: ProxyRepository,
    vault: WindowsCredentialVault,
) -> int:
    """Creates one profile: SamMonny daemon profile (local fallback when the daemon is unreachable),
    cookies, Vault token. Blocking network + disk + DB work: run it off the GUI thread."""
    from src.application.services.gologin_sync_service import GoLoginSyncService

    sync_svc = GoLoginSyncService(profile_repo=profile_repo, project_repo=project_repo, proxy_repo=proxy_repo)
    try:
        profile_id = sync_svc.create_real_gologin_profile(
            name=name, project_id=project_id, proxy_id=proxy_id, cookie=cookie if cookie else None
        )
    except Exception as e:
        # Daemon unreachable (or a step after its creation failed: that daemon profile was deleted again).
        logger.warning("Daemon profile creation failed (%s): creating a local profile", e)
        profile_id = sync_svc.create_local_profile(
            name=name, project_id=project_id, proxy_id=proxy_id, cookie=cookie if cookie else None
        )

    # AgentShield: Save access token to Windows Vault DPAPI
    if token and profile_id:
        vault.save_oauth_tokens(profile_id=profile_id, access_token=token)
    return int(profile_id)


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
        parent: QWidget | None = None,
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

    def exec(self) -> int:
        """Explicit Python wrapper over QDialog.exec for testability and lifecycle hooks."""
        return super().exec()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*STANDARD_DIALOG_MARGINS)
        layout.setSpacing(STANDARD_DIALOG_SPACING)

        is_edit = bool(self.profile_data and self.profile_data.get("id"))
        header = create_dialog_header(
            icon=FluentIcon.EDIT if is_edit else FluentIcon.ADD,
            title="Chỉnh Sửa Hồ Sơ TikTok" if is_edit else "Thêm Hồ Sơ TikTok Mới",
            subtitle="Cấu hình thông tin tài khoản, dự án phân bổ, proxy kết nối và thông tin xác thực.",
            parent=self,
        )
        layout.addWidget(header)

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

        # Stored cookies live in cookies_browser / cookies_json (there is no "cookie" column).
        self._original_cookie = str(
            self.profile_data.get("cookies_browser")
            or self.profile_data.get("cookies_json")
            or self.profile_data.get("cookie")
            or ""
        )
        self.cookie_input.setPlainText(self._original_cookie)

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
            }
            # Only write cookies when the user actually changed them ("cookie" is not a column and
            # was silently dropped before; an untouched field must not overwrite stored cookies).
            cookie_changed = cookie != getattr(self, "_original_cookie", "").strip()
            if cookie_changed:
                update_payload["cookies_json"] = cookie if cookie else None
            if (cookie_changed and cookie) or token:
                update_payload["status"] = "LIVE"
            self.profile_repo.update(profile_id, update_payload)

            if token:
                # Keep the stored refresh token (overwriting the whole payload lost it); the expiry of a
                # pasted token is unknown, so it is refreshed on first use when a refresh token exists.
                payload = dict(self.vault.get_oauth_tokens(profile_id) or {})
                payload.update(access_token=token, expires_at=None)
                self.vault.save_oauth_payload(profile_id, payload)
                self.profile_repo.update(profile_id, api_reconnect_required=0)

            self.accept()
            return

        # New profile: daemon call + cookie seeding + DB writes off the GUI thread.
        self.btn_save.setEnabled(False)
        self.btn_save.setText("Đang tạo hồ sơ...")

        def created(_profile_id: int) -> None:
            if not sip.isdeleted(self):
                self.accept()

        def failed(err: str) -> None:
            logger.error("Profile creation failed: %s", err)
            if sip.isdeleted(self):
                return
            self.btn_save.setEnabled(True)
            self.btn_save.setText("Lưu Hồ Sơ")
            InfoBar.error(title="Lỗi Tạo Hồ Sơ", content=err, position=InfoBarPosition.TOP, parent=self)

        run_task(
            create_profile,
            name=name,
            project_id=project_id,
            proxy_id=proxy_id,
            cookie=cookie,
            token=token,
            profile_repo=self.profile_repo,
            project_repo=self.project_repo,
            proxy_repo=self.proxy_repo,
            vault=self.vault,
            on_result=created,
            on_error=failed,
        )
