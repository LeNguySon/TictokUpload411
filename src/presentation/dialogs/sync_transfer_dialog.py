"""
Sync & Transfer Dialog: Export and Import profiles, proxies, and project datasets (Zip / JSON).
"""

import json
import logging
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PyQt6 import sip
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QRadioButton,
    QTabWidget,
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
    PrimaryPushButton,
    PushButton,
)

from src.application.workers.task_worker import run_task
from src.infrastructure.credentials.backup_crypto import decrypt_bundle, encrypt_bundle
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
from src.presentation.dialogs.dialog_helpers import (
    STANDARD_DIALOG_MARGINS,
    STANDARD_DIALOG_SPACING,
    create_dialog_header,
    style_tab_widget,
)

logger = logging.getLogger(__name__)


LEGACY_MANIFEST = "dataset_manifest.json"
ENCRYPTED_MANIFEST = "dataset_manifest.json.enc"
MIN_PASSPHRASE_LEN = 8


def bundle_is_encrypted(zip_path: str | Path) -> bool:
    """True for passphrase-encrypted bundles, False for legacy plaintext ones."""
    with zipfile.ZipFile(Path(zip_path), "r") as zf:
        return ENCRYPTED_MANIFEST in zf.namelist()


def export_project_dataset(
    zip_path: str | Path,
    project_id: int | None,
    profile_repo: ProfileRepository,
    proxy_repo: ProxyRepository,
    project_repo: ProjectRepository,
    include_proxies: bool = True,
    passphrase: str | None = None,
) -> int:
    """Exports active profiles and associated proxies to a portable zip bundle.

    The manifest carries cookies and passwords, so it is always encrypted with ``passphrase``
    (``dataset_manifest.json.enc``, see backup_crypto); there is no plaintext export any more."""
    if not passphrase:
        raise ValueError("Cần đặt mật khẩu cho file sao lưu (file chứa cookie và mật khẩu)")
    profiles = profile_repo.list_active(project_id=project_id)
    proxies = proxy_repo.list_all() if include_proxies else []
    projects = project_repo.list_all()

    manifest: dict[str, Any] = {
        "version": "1.0.0",
        "exported_profiles_count": len(profiles),
        "profiles": profiles,
        "proxies": proxies,
        "projects": projects,
    }

    out_zip = Path(zip_path)
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        payload = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
        zf.writestr(ENCRYPTED_MANIFEST, encrypt_bundle(payload, passphrase))

    return len(profiles)


def import_project_dataset(
    zip_path: str | Path,
    profile_repo: ProfileRepository,
    proxy_repo: ProxyRepository,
    project_repo: ProjectRepository | None = None,
    overwrite: bool = False,
    passphrase: str | None = None,
) -> tuple[int, int]:
    """Imports profiles and proxies from a zip bundle into the database.

    Encrypted bundles need ``passphrase`` (BackupPasswordError when wrong); legacy plaintext bundles
    (``dataset_manifest.json``) are still accepted."""
    in_zip = Path(zip_path)
    if not in_zip.exists():
        raise FileNotFoundError(f"File không tồn tại: {zip_path}")

    with zipfile.ZipFile(in_zip, "r") as zf:
        names = zf.namelist()
        if ENCRYPTED_MANIFEST in names:
            content = decrypt_bundle(zf.read(ENCRYPTED_MANIFEST), passphrase or "").decode("utf-8")
        elif LEGACY_MANIFEST in names:
            content = zf.read(LEGACY_MANIFEST).decode("utf-8")
        else:
            raise ValueError("File sao lưu không hợp lệ (thiếu dataset_manifest)")
        manifest = json.loads(content)

    profiles_imported = 0
    proxies_imported = 0
    project_id_map: dict[int, int] = {}

    # Import projects if repository provided
    if project_repo:
        existing_projects = {p["name"]: p["id"] for p in project_repo.list_all()}
        for proj in manifest.get("projects", []):
            name = proj.get("name")
            if not name:
                continue
            if name in existing_projects:
                project_id_map[proj["id"]] = existing_projects[name]
            else:
                try:
                    new_id = project_repo.create(name=name, description=proj.get("description"))
                    project_id_map[proj["id"]] = new_id
                    existing_projects[name] = new_id
                except Exception as ignored:
                    logger.debug("import_project_dataset: ignored error: %s", ignored)

    # Import proxies
    proxy_id_map: dict[int, int] = {}
    for px in manifest.get("proxies", []):
        try:
            px_id = proxy_repo.create(
                host=px["host"],
                port=px["port"],
                protocol=px.get("protocol", "http"),
                username=px.get("username"),
                password=px.get("password"),
            )
            proxies_imported += 1
            if "id" in px and px_id:
                proxy_id_map[px["id"]] = px_id
        except Exception as ignored:
            logger.debug("import_project_dataset: ignored error: %s", ignored)

    # Import profiles
    for pf in manifest.get("profiles", []):
        raw_proj_id = pf.get("project_id")
        target_proj_id = project_id_map.get(raw_proj_id, raw_proj_id) if raw_proj_id else None

        raw_px_id = pf.get("proxy_id")
        # Only a proxy imported in THIS run: the source id may be a different proxy here.
        target_px_id = proxy_id_map.get(raw_px_id) if raw_px_id else None

        # Attempt creation with mapped FKs, fallback to None if FK violates
        try:
            profile_repo.create(
                name=pf.get("name", "Imported Profile"),
                project_id=target_proj_id,
                proxy_id=target_px_id,
                tiktok_id=pf.get("username_on_tiktok") or pf.get("tiktok_id"),
                cookie=pf.get("cookies_json") or pf.get("cookie"),
                status=pf.get("status", "stopped"),
            )
            profiles_imported += 1
        except Exception:
            try:
                # Fallback without foreign keys
                profile_repo.create(
                    name=pf.get("name", "Imported Profile"),
                    project_id=None,
                    proxy_id=None,
                    tiktok_id=pf.get("username_on_tiktok") or pf.get("tiktok_id"),
                    cookie=pf.get("cookies_json") or pf.get("cookie"),
                    status=pf.get("status", "stopped"),
                )
                profiles_imported += 1
            except Exception as e:
                logger.warning("Could not import profile %s: %s", pf.get("name"), e)

    return profiles_imported, proxies_imported


class SyncTransferDialog(QDialog):
    """
    Dialog for Exporting ('Gửi') and Importing ('Nhận') profiles, proxies, and project datasets.
    """

    def __init__(
        self,
        project_repo: ProjectRepository,
        profile_repo: ProfileRepository,
        proxy_repo: ProxyRepository,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.project_repo = project_repo
        self.profile_repo = profile_repo
        self.proxy_repo = proxy_repo

        self.setWindowTitle("Nhận và Gửi Dữ Liệu (Sao Lưu & Khôi Phục)")
        self.resize(580, 420)
        self._init_ui()

    def exec(self) -> int:
        """Explicit Python wrapper over QDialog.exec for testability and lifecycle hooks."""
        return super().exec()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(*STANDARD_DIALOG_MARGINS)
        main_layout.setSpacing(STANDARD_DIALOG_SPACING)

        header = create_dialog_header(
            icon=FluentIcon.SYNC,
            title="Nhận và Gửi Dữ Liệu (Sao Lưu & Khôi Phục)",
            subtitle="Xuất hoặc nhập trọn bộ cấu hình hồ sơ, proxy và dự án dưới dạng gói dữ liệu nén .zip.",
            parent=self,
        )
        main_layout.addWidget(header)

        self.tabs = style_tab_widget(QTabWidget(self))

        # Tab 1: Gửi (Xuất dữ liệu)
        tab_export = QWidget()
        exp_layout = QVBoxLayout(tab_export)
        exp_layout.setSpacing(10)

        exp_layout.addWidget(QLabel("<b>1. Chọn phạm vi dự án cần xuất:</b>"))
        self.combo_project_export = ComboBox(tab_export)
        self.combo_project_export.addItem("Toàn bộ dữ liệu (Tất cả dự án)", userData=None)
        for p in self.project_repo.list_all():
            self.combo_project_export.addItem(p["name"], userData=p["id"])
        exp_layout.addWidget(self.combo_project_export)

        self.chk_include_proxies = CheckBox("Kèm theo danh sách Proxy liên kết", tab_export)
        self.chk_include_proxies.setChecked(True)
        exp_layout.addWidget(self.chk_include_proxies)

        exp_layout.addWidget(QLabel("<b>2. Đường dẫn file nén sao lưu (.zip):</b>"))
        file_exp_layout = QHBoxLayout()
        self.txt_export_path = LineEdit(tab_export)
        self.txt_export_path.setText(str(Path.cwd() / "backup_tiktok_profiles.zip"))
        btn_browse_exp = PushButton("Chọn...", tab_export)
        btn_browse_exp.clicked.connect(self._on_browse_export)
        file_exp_layout.addWidget(self.txt_export_path, 1)
        file_exp_layout.addWidget(btn_browse_exp)
        exp_layout.addLayout(file_exp_layout)

        exp_layout.addStretch()
        self.btn_start_export = PrimaryPushButton(FluentIcon.SHARE, "Bắt Đầu Đóng Gói && Xuất Dữ Liệu", tab_export)
        self.btn_start_export.clicked.connect(self._on_start_export)
        exp_layout.addWidget(self.btn_start_export)

        self.tabs.addTab(tab_export, "Gửi (Sao Lưu)")

        # Tab 2: Nhận (Khôi phục dữ liệu)
        tab_import = QWidget()
        imp_layout = QVBoxLayout(tab_import)
        imp_layout.setSpacing(10)

        imp_layout.addWidget(QLabel("<b>1. Chọn gói dữ liệu sao lưu (.zip):</b>"))
        file_imp_layout = QHBoxLayout()
        self.txt_import_path = LineEdit(tab_import)
        self.txt_import_path.setPlaceholderText("Đường dẫn đến file .zip...")
        btn_browse_imp = PushButton("Chọn...", tab_import)
        btn_browse_imp.clicked.connect(self._on_browse_import)
        file_imp_layout.addWidget(self.txt_import_path, 1)
        file_imp_layout.addWidget(btn_browse_imp)
        imp_layout.addLayout(file_imp_layout)

        imp_layout.addWidget(QLabel("<b>2. Cơ chế xử lý hồ sơ trùng lặp:</b>"))
        self.btn_group_dup = QButtonGroup(tab_import)
        self.rb_skip = QRadioButton("Bỏ qua nếu hồ sơ đã tồn tại (Khuyên dùng)", tab_import)
        self.rb_skip.setChecked(True)
        self.rb_overwrite = QRadioButton("Ghi đè cập nhật hồ sơ cũ", tab_import)
        self.btn_group_dup.addButton(self.rb_skip)
        self.btn_group_dup.addButton(self.rb_overwrite)
        imp_layout.addWidget(self.rb_skip)
        imp_layout.addWidget(self.rb_overwrite)

        imp_layout.addStretch()
        self.btn_start_import = PrimaryPushButton(FluentIcon.DOWNLOAD, "Bắt Đầu Nhận && Khôi Phục Dữ Liệu", tab_import)
        self.btn_start_import.clicked.connect(self._on_start_import)
        imp_layout.addWidget(self.btn_start_import)

        self.tabs.addTab(tab_import, "Nhận (Khôi Phục)")

        main_layout.addWidget(self.tabs)

        # Footer Action
        footer_layout = QHBoxLayout()
        btn_close = PushButton("Đóng", self)
        btn_close.clicked.connect(self.accept)
        footer_layout.addStretch()
        footer_layout.addWidget(btn_close)
        main_layout.addLayout(footer_layout)

    def _on_browse_export(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Lưu Gói Sao Lưu",
            self.txt_export_path.text(),
            "Zip Archive (*.zip)",
        )
        if file_path:
            self.txt_export_path.setText(file_path)

    def _on_browse_import(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn Gói Dữ Liệu Cần Nhận",
            "",
            "Zip Archive (*.zip)",
        )
        if file_path:
            self.txt_import_path.setText(file_path)

    def _on_start_export(self) -> None:
        out_path = self.txt_export_path.text().strip()
        if not out_path:
            InfoBar.warning(
                title="Lỗi Đường Dẫn",
                content="Vui lòng chỉ định đường dẫn lưu file .zip.",
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return

        passphrase = self._ask_passphrase(confirm=True)
        if not passphrase:
            return
        self._run_job(
            self.btn_start_export,
            export_project_dataset,
            {
                "passphrase": passphrase,
                "zip_path": out_path,
                "project_id": self.combo_project_export.currentData(),
                "profile_repo": self.profile_repo,
                "proxy_repo": self.proxy_repo,
                "project_repo": self.project_repo,
                "include_proxies": self.chk_include_proxies.isChecked(),
            },
            ok_title="Xuất Dữ Liệu Thành Công",
            ok_text=lambda count: f"Đã đóng gói thành công {count} hồ sơ ra file: {out_path}",
            fail_title="Xuất Dữ Liệu Thất Bại",
        )

    def _on_start_import(self) -> None:
        in_path = self.txt_import_path.text().strip()
        if not in_path or not Path(in_path).exists():
            InfoBar.warning(
                title="File Không Hợp Lệ",
                content="Vui lòng chọn file .zip hợp lệ trên máy tính.",
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return

        try:
            encrypted = bundle_is_encrypted(in_path)
        except (OSError, zipfile.BadZipFile) as e:
            InfoBar.error(title="File Không Hợp Lệ", content=str(e), position=InfoBarPosition.TOP, parent=self)
            return
        passphrase = None
        if encrypted:
            passphrase = self._ask_passphrase(confirm=False)
            if not passphrase:
                return
        else:
            InfoBar.warning(
                title="File Sao Lưu Không Mã Hoá",
                content="File này là bản cũ, chứa cookie/mật khẩu dạng chữ thường. Hãy xoá file sau khi nhập.",
                position=InfoBarPosition.TOP,
                duration=8000,
                parent=self,
            )
        self._run_job(
            self.btn_start_import,
            import_project_dataset,
            {
                "passphrase": passphrase,
                "zip_path": in_path,
                "profile_repo": self.profile_repo,
                "proxy_repo": self.proxy_repo,
                "project_repo": self.project_repo,
                "overwrite": self.rb_overwrite.isChecked(),
            },
            ok_title="Nhận Dữ Liệu Thành Công",
            ok_text=lambda counts: f"Đã khôi phục {counts[0]} hồ sơ và {counts[1]} proxy vào CSDL.",
            fail_title="Nhận Dữ Liệu Thất Bại",
        )

    def _ask_passphrase(self, confirm: bool) -> str | None:
        """Asks for the bundle passphrase (twice when exporting). None when cancelled or invalid."""
        first, ok = QInputDialog.getText(
            self,
            "Mật Khẩu File Sao Lưu",
            f"Mật khẩu (tối thiểu {MIN_PASSPHRASE_LEN} ký tự). File chứa cookie và mật khẩu của hồ sơ:"
            if confirm
            else "Nhập mật khẩu của file sao lưu:",
            QLineEdit.EchoMode.Password,
        )
        if not ok or not first:
            return None
        if confirm:
            if len(first) < MIN_PASSPHRASE_LEN:
                InfoBar.warning(
                    title="Mật Khẩu Quá Ngắn",
                    content=f"Cần ít nhất {MIN_PASSPHRASE_LEN} ký tự.",
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
                return None
            again, ok = QInputDialog.getText(
                self, "Xác Nhận Mật Khẩu", "Nhập lại mật khẩu:", QLineEdit.EchoMode.Password
            )
            if not ok or again != first:
                InfoBar.warning(
                    title="Mật Khẩu Không Khớp",
                    content="Hai lần nhập mật khẩu không giống nhau.",
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
                return None
        return str(first)

    def _run_job(
        self,
        button: Any,
        fn: Callable[..., Any],
        kwargs: dict[str, Any],
        *,
        ok_title: str,
        ok_text: Callable[[Any], str],
        fail_title: str,
    ) -> None:
        """Runs an export/import (zip + many SQLite writes) off the GUI thread; one job per button."""
        button.setEnabled(False)

        def finish() -> bool:
            if sip.isdeleted(self):
                return False
            button.setEnabled(True)
            return True

        def ok(result: Any) -> None:
            if finish():
                InfoBar.success(title=ok_title, content=ok_text(result), position=InfoBarPosition.TOP, parent=self)

        def failed(err: str) -> None:
            logger.error("%s: %s", fail_title, err)
            if finish():
                InfoBar.error(title=fail_title, content=err, position=InfoBarPosition.TOP, parent=self)

        run_task(fn, on_result=ok, on_error=failed, **kwargs)
