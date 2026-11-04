"""
Main Application Window: Windows 11 Fluent Design Dual-Table Layout matching SSMATool parity.
"""

import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QPoint, QSettings, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    Action,
    ComboBox,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    MessageBox,
    PrimaryPushButton,
    PushButton,
    RoundMenu,
    SearchLineEdit,
    SpinBox,
    SwitchButton,
    Theme,
    TransparentToolButton,
    setTheme,
)

from src.application.services.gologin_sync_service import GoLoginSyncService
from src.application.services.profile_service import ProfileService
from src.application.services.proxy_service import ProxyService
from src.application.services.upload_service import UploadService
from src.application.signals.app_signals import AppSignalBus
from src.application.workers.metrics_sync_worker import MetricsSyncWorker
from src.application.workers.thread_pool_manager import ThreadPoolManager
from src.application.workers.upload_worker import UploadWorker
from src.infrastructure.browser.orbita_launcher import OrbitaLauncher
from src.infrastructure.browser.sammonny_daemon_manager import SamMonnyDaemonSupervisor
from src.infrastructure.credentials.windows_vault import WindowsCredentialVault
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
from src.infrastructure.database.repositories.video_repository import VideoRepository
from src.infrastructure.tiktok.passive_sync_service import PassiveTikTokSyncService
from src.infrastructure.tiktok.sammonny_adapter import SamMonnyTikTokAdapter
from src.presentation.dialogs.add_profile_dialog import AddProfileDialog
from src.presentation.dialogs.api_cookie_dialog import ApiCookieDialog
from src.presentation.dialogs.assign_project_dialog import AssignProjectDialog
from src.presentation.dialogs.assign_proxy_dialog import AssignProxyDialog
from src.presentation.dialogs.batch_folder_upload_dialog import BatchFolderUploadDialog
from src.presentation.dialogs.bulk_add_profile_dialog import BulkAddProfileDialog
from src.presentation.dialogs.bulk_edit_profile_dialog import BulkEditProfileDialog
from src.presentation.dialogs.permissions_dialog import PermissionsDialog
from src.presentation.dialogs.project_dialog import ProjectManagerDialog
from src.presentation.dialogs.proxy_dialog import ProxyManagerDialog
from src.presentation.dialogs.schedule_dialog import ScheduleVideoDialog
from src.presentation.dialogs.sync_transfer_dialog import SyncTransferDialog
from src.presentation.dialogs.table_settings_dialog import TableSettingsDialog
from src.presentation.dialogs.trash_dialog import TrashDialog
from src.presentation.dialogs.user_guide_dialog import UserGuideDialog
from src.presentation.dialogs.video_metadata_dialog import VideoMetadataDialog
from src.presentation.widgets.profile_table_widget import ProfileTableWidget
from src.presentation.widgets.video_queue_table_widget import VideoQueueTableWidget

logger = logging.getLogger(__name__)


class TikTokManagerMainWindow(QMainWindow):
    """
    Main Desktop Window implementing the dual-table vertical splitter layout
    with full Windows 11 Fluent UI aesthetics and multithreaded backend integration.
    """

    def __init__(
        self,
        db_path: Path | str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.db_path = db_path
        setTheme(Theme.LIGHT)

        # Repositories
        self.project_repo = ProjectRepository(self.db_path)
        self.proxy_repo = ProxyRepository(self.db_path)
        self.profile_repo = ProfileRepository(self.db_path)
        self.video_repo = VideoRepository(self.db_path)

        # Infrastructure & Vault
        self.vault = WindowsCredentialVault()
        self.tiktok_adapter = SamMonnyTikTokAdapter(vault=self.vault)
        self.orbita_launcher = OrbitaLauncher()

        # Signal Bus & Concurrency Manager
        self.signal_bus = AppSignalBus.instance()
        self.thread_pool = ThreadPoolManager.instance()

        # Application Services
        self.proxy_service = ProxyService(proxy_repo=self.proxy_repo)
        self.passive_sync_service = PassiveTikTokSyncService(
            profile_repo=self.profile_repo,
            proxy_repo=self.proxy_repo,
            signal_bus=self.signal_bus,
        )
        self.profile_service = ProfileService(
            profile_repo=self.profile_repo,
            proxy_repo=self.proxy_repo,
            tiktok_adapter=self.tiktok_adapter,
            sync_service=self.passive_sync_service,
        )
        self.upload_service = UploadService(
            profile_repo=self.profile_repo,
            video_repo=self.video_repo,
            tiktok_adapter=self.tiktok_adapter,
        )

        # SamMonny Native Daemon & GoLogin Sync Service
        self.daemon_supervisor = SamMonnyDaemonSupervisor()
        self.gologin_sync_service = GoLoginSyncService(
            profile_repo=self.profile_repo,
            project_repo=self.project_repo,
            proxy_repo=self.proxy_repo,
            daemon_supervisor=self.daemon_supervisor,
        )
        self.thread_pool.executor.submit(self.daemon_supervisor.ensure_daemon_running)

        # UI Preferences & Persistent Settings
        settings = QSettings("TAVM", "TikTokManager")
        saved_hidden = settings.value("hidden_profile_columns", "")
        self.hidden_columns: set[int] = set()
        if saved_hidden:
            try:
                self.hidden_columns = {int(x) for x in str(saved_hidden).split(",") if x.strip()}
            except (ValueError, TypeError):
                self.hidden_columns = set()

        self.setWindowTitle("SSMATool Reup Tiktok - TAVM 2026 Windows 11 Edition")
        self.resize(1366, 850)

        self._init_ui()
        # Apply persistent column visibility
        for col_idx in range(self.profile_table.columnCount()):
            self.profile_table.setColumnHidden(col_idx, col_idx in self.hidden_columns)
        self._connect_signals()
        self.refresh_all_data()

        # Real-time Video Schedule Auto-Dispatch Timer (Every 15s)
        self.scheduler_timer = QTimer(self)
        self.scheduler_timer.setInterval(15000)
        self.scheduler_timer.timeout.connect(self._check_scheduled_queue)
        self.scheduler_timer.start()

    def _init_ui(self) -> None:
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(6)

        # 1. Dual-Table Splitter
        self.splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.splitter.setHandleWidth(6)

        # --- Top Section: Profiles ---
        top_container = QWidget(self.splitter)
        top_layout = QVBoxLayout(top_container)
        top_layout.setContentsMargins(0, 0, 0, 4)
        top_layout.setSpacing(6)

        # Profiles Header Toolbar: Clean Minimalist Bar (Dự án + Tìm kiếm + Icon Cài Đặt)
        top_toolbar = QHBoxLayout()
        top_toolbar.setContentsMargins(6, 4, 6, 6)
        top_toolbar.setSpacing(10)

        lbl_proj = QLabel("Dự án:", self)
        lbl_proj.setStyleSheet("font-weight: 600; font-size: 13px; color: #201F1E;")
        lbl_proj.setFixedHeight(34)
        top_toolbar.addWidget(lbl_proj)

        self.project_combo = ComboBox(self)
        self.project_combo.setFixedHeight(34)
        self.project_combo.setFixedWidth(220)
        self.project_combo.currentIndexChanged.connect(self._on_project_changed)
        top_toolbar.addWidget(self.project_combo)

        self.search_profile = SearchLineEdit(self)
        self.search_profile.setFixedHeight(34)
        self.search_profile.setClearButtonEnabled(True)
        self.search_profile.setPlaceholderText("Tìm theo id | profile | email | proxy...")
        self.search_profile.textChanged.connect(self._on_search_profile)
        top_toolbar.addWidget(self.search_profile, 1)

        # Unified Settings & Tools Menu Button (Clean 36x36 with 20x20 Vector FluentIcon - Zero Dropdown Arrow)
        self.btn_settings = TransparentToolButton(FluentIcon.SETTING, self)
        self.btn_settings.setFixedSize(36, 36)
        self.btn_settings.setIconSize(QSize(20, 20))
        self.btn_settings.setToolTip("Cài đặt & Tất cả công cụ quản trị")
        self.btn_settings.clicked.connect(self._show_settings_menu)
        self._init_settings_menu()
        top_toolbar.addWidget(self.btn_settings)

        top_layout.addLayout(top_toolbar)

        # Profile Table
        self.profile_table = ProfileTableWidget(top_container)
        top_layout.addWidget(self.profile_table)

        # --- Bottom Section: Videos & Queue ---
        bottom_container = QWidget(self.splitter)
        bottom_layout = QVBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(0, 4, 0, 0)
        bottom_layout.setSpacing(6)

        # Video Header Toolbar: Scientific sizing, uniform 34px height, crisp vector FluentIcons
        bottom_toolbar = QHBoxLayout()
        bottom_toolbar.setContentsMargins(6, 4, 6, 4)
        bottom_toolbar.setSpacing(8)

        self.lbl_video_header = QLabel("Bảng video (Đã chọn 0 / 0)", self)
        self.lbl_video_header.setStyleSheet("font-weight: 600; font-size: 13px; color: #201F1E;")
        self.lbl_video_header.setFixedHeight(34)
        bottom_toolbar.addWidget(self.lbl_video_header)

        self.btn_schedule = PushButton(FluentIcon.CALENDAR, "Lên lịch", self)
        self.btn_schedule.setFixedHeight(34)
        self.btn_schedule.setIconSize(QSize(16, 16))
        self.btn_schedule.clicked.connect(self._on_schedule_videos)
        bottom_toolbar.addWidget(self.btn_schedule)

        self.btn_pick_pc = PrimaryPushButton(FluentIcon.VIDEO, "Thêm Video", self)
        self.btn_pick_pc.setFixedHeight(34)
        self.btn_pick_pc.setIconSize(QSize(16, 16))
        self.btn_pick_pc.clicked.connect(self._on_pick_video_files)
        bottom_toolbar.addWidget(self.btn_pick_pc)

        self.btn_batch_upload = PushButton(FluentIcon.FOLDER, "Nạp Thư Mục & Phân Bổ", self)
        self.btn_batch_upload.setFixedHeight(34)
        self.btn_batch_upload.setIconSize(QSize(16, 16))
        self.btn_batch_upload.clicked.connect(self._on_open_batch_folder_upload)
        bottom_toolbar.addWidget(self.btn_batch_upload)

        self.btn_start_upload = PrimaryPushButton(FluentIcon.UP, "Bắt đầu Upload", self)
        self.btn_start_upload.setFixedHeight(34)
        self.btn_start_upload.setIconSize(QSize(16, 16))
        self.btn_start_upload.clicked.connect(self._on_start_upload_queue)
        bottom_toolbar.addWidget(self.btn_start_upload)

        lbl_jump = QLabel("Nhảy dòng:", self)
        lbl_jump.setStyleSheet("font-size: 12px; color: #605E5C;")
        lbl_jump.setFixedHeight(34)
        bottom_toolbar.addWidget(lbl_jump)

        self.spin_jump = SpinBox(self)
        self.spin_jump.setFixedHeight(34)
        self.spin_jump.setFixedWidth(70)
        self.spin_jump.setValue(0)
        bottom_toolbar.addWidget(self.spin_jump)

        self.search_video = SearchLineEdit(self)
        self.search_video.setFixedHeight(34)
        self.search_video.setClearButtonEnabled(True)
        self.search_video.setPlaceholderText("Tìm video theo tiêu đề trong bảng...")
        self.search_video.textChanged.connect(self._on_search_video)
        bottom_toolbar.addWidget(self.search_video, 1)

        self.btn_clear_videos = PushButton(FluentIcon.DELETE, "Xóa bảng", self)
        self.btn_clear_videos.setFixedHeight(34)
        self.btn_clear_videos.setIconSize(QSize(16, 16))
        self.btn_clear_videos.clicked.connect(self._on_clear_video_table)
        bottom_toolbar.addWidget(self.btn_clear_videos)

        self.switch_auto = SwitchButton(self)
        self.switch_auto.setFixedHeight(34)
        self.switch_auto.setChecked(True)
        self.switch_auto.setToolTip("Tự động chuyển tiếp hàng đợi")
        bottom_toolbar.addWidget(self.switch_auto)

        bottom_layout.addLayout(bottom_toolbar)

        # Video Queue Table
        self.video_table = VideoQueueTableWidget(bottom_container)
        bottom_layout.addWidget(self.video_table)

        # Set initial splitter proportions (55% top, 45% bottom)
        self.splitter.addWidget(top_container)
        self.splitter.addWidget(bottom_container)
        self.splitter.setSizes([460, 340])
        main_layout.addWidget(self.splitter, 1)

        # 3. Footer / Status Bar
        footer = QHBoxLayout()
        self.lbl_footer_status = QLabel(
            "Xin chào user | Thời gian hết hạn: 07-08-2026 | Gói: Goepro | Version: 1.5.5.2",
            self,
        )
        self.lbl_footer_status.setStyleSheet("color: #605E5C; font-size: 11px;")
        footer.addWidget(self.lbl_footer_status)
        footer.addStretch()

        self.chk_clean_exit = QCheckBox("Dọn cache tất cả dự án trước khi thoát", self)
        self.chk_clean_exit.setChecked(True)
        footer.addWidget(self.chk_clean_exit)
        main_layout.addLayout(footer)

        # 4. Global Keyboard Shortcuts
        self.shortcut_f5 = QShortcut(QKeySequence("F5"), self)
        self.shortcut_f5.activated.connect(self.refresh_all_data)
        self.shortcut_ctrl_r = QShortcut(QKeySequence("Ctrl+R"), self)
        self.shortcut_ctrl_r.activated.connect(self.refresh_all_data)

    def _connect_signals(self) -> None:
        self.signal_bus.upload_progress.connect(self._on_upload_progress)
        self.signal_bus.upload_completed.connect(self._on_upload_completed)
        self.signal_bus.upload_failed.connect(self._on_upload_failed)
        self.signal_bus.profile_updated.connect(self._on_profile_updated)

        # Context Menu Events on Profile Table
        self.profile_table.open_orbita_requested.connect(self._on_launch_orbita)
        self.profile_table.close_orbita_requested.connect(self._on_close_orbita)
        self.profile_table.check_cookie_requested.connect(self._on_check_single_cookie)
        self.profile_table.sync_metrics_requested.connect(self._on_sync_selected_metrics)
        self.profile_table.add_video_requested.connect(self._on_add_video_for_profiles)
        self.profile_table.update_proxy_requested.connect(self._on_update_profiles_proxy)
        self.profile_table.change_project_requested.connect(self._on_change_profiles_project)
        self.profile_table.bulk_edit_requested.connect(self._on_bulk_edit_profiles)
        self.profile_table.edit_profile_requested.connect(self._on_edit_profile)
        self.profile_table.open_web_profile_requested.connect(self._on_open_tiktok_web)
        self.profile_table.open_folder_requested.connect(self._on_open_profile_folder)
        self.profile_table.change_status_requested.connect(self._on_change_profile_status)
        self.profile_table.soft_delete_requested.connect(self._on_soft_delete_profiles)
        self.profile_table.remove_proxy_requested.connect(self._on_remove_proxy_selected)
        self.profile_table.rotate_proxy_requested.connect(self._on_rotate_proxy_selected)
        self.profile_table.check_proxy_requested.connect(self._on_check_proxy_selected)

        # Context Menu & Selection Events on Video Table
        self.video_table.upload_now_requested.connect(self._on_upload_single_video)
        self.video_table.schedule_video_requested.connect(self._on_schedule_videos_from_table)
        self.video_table.edit_metadata_requested.connect(self._on_edit_video_metadata)
        self.video_table.preview_video_requested.connect(self._on_preview_video)
        self.video_table.open_folder_requested.connect(self._on_open_video_folder)
        self.video_table.open_published_link_requested.connect(self._on_open_published_link)
        self.video_table.delete_video_requested.connect(self._on_delete_selected_videos)
        self.video_table.itemSelectionChanged.connect(self._on_video_selection_changed)
        self.video_table.files_dropped.connect(self._on_videos_dropped)

    def refresh_all_data(self) -> None:
        self._refresh_project_dropdown()
        self.refresh_profiles()
        self.refresh_videos()

    def _refresh_project_dropdown(self) -> None:
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        self.project_combo.addItem("Tất cả dự án", userData=None)
        projects = self.project_repo.list_all()
        for p in projects:
            self.project_combo.addItem(p["name"], userData=p["id"])
        self.project_combo.blockSignals(False)

    def refresh_profiles(self) -> None:
        project_id = self.project_combo.currentData()
        profiles = self.profile_repo.list_active(project_id=project_id)
        self.profile_table.load_profiles(profiles)

    def refresh_videos(self) -> None:
        available = self.video_repo.list_available()
        self.video_table.load_videos(available)
        self.lbl_video_header.setText(f"Bảng video Đã chọn 0 / {len(available)}")

    def _on_project_changed(self) -> None:
        self.refresh_profiles()

    def _on_search_profile(self, text: str) -> None:
        filter_text = text.strip().lower()
        for row in range(self.profile_table.rowCount()):
            matched = False
            for col in (2, 4, 6, 11):  # Name, Proxy, ID Tiktok, Email
                item = self.profile_table.item(row, col)
                if item and filter_text in item.text().lower():
                    matched = True
                    break
            self.profile_table.setRowHidden(row, not matched if filter_text else False)

    def _on_search_video(self, text: str) -> None:
        filter_text = text.strip().lower()
        for row in range(self.video_table.rowCount()):
            item = self.video_table.item(row, 1)  # Col 1: Tiêu đề
            matched = not filter_text or (item and filter_text in item.text().lower())
            self.video_table.setRowHidden(row, not matched)

    def _on_video_selection_changed(self) -> None:
        selected_rows = {index.row() for index in self.video_table.selectedIndexes()}
        total_rows = self.video_table.rowCount()
        self.lbl_video_header.setText(f"Bảng video Đã chọn {len(selected_rows)} / {total_rows}")

    def _init_settings_menu(self) -> None:
        """Centralized Settings & Tools Menu housing all administrative actions."""
        self.settings_menu = RoundMenu(parent=self)

        # 1. Thao tác hồ sơ
        act_add_1 = Action(FluentIcon.ADD, "Add 1 profile (Thêm 1 hồ sơ)", self)
        act_add_1.triggered.connect(self._on_add_profile)
        self.settings_menu.addAction(act_add_1)

        act_add_many = Action(FluentIcon.FOLDER_ADD, "Add nhiều profile (Hàng loạt)", self)
        act_add_many.triggered.connect(self._on_bulk_add_profiles)
        self.settings_menu.addAction(act_add_many)

        act_show_all = Action(FluentIcon.VIEW, "Show all (Hiển thị tất cả hồ sơ)", self)
        act_show_all.triggered.connect(self._on_show_all_profiles)
        self.settings_menu.addAction(act_show_all)

        act_sync = Action(FluentIcon.SYNC, "Đồng bộ số liệu TikTok", self)
        act_sync.triggered.connect(self._on_sync_selected_metrics)
        self.settings_menu.addAction(act_sync)

        act_orbita = Action(FluentIcon.GLOBE, "Mở Trình duyệt Orbita Antidetect", self)
        act_orbita.triggered.connect(self._on_launch_orbita_selected)
        self.settings_menu.addAction(act_orbita)

        act_gologin_sync = Action(FluentIcon.CLOUD_DOWNLOAD, "Đồng bộ Profile GoLogin SDK (22+ có sẵn)", self)
        act_gologin_sync.triggered.connect(self._on_sync_gologin_profiles)
        self.settings_menu.addAction(act_gologin_sync)

        self.settings_menu.addSeparator()

        # 2. Quản lý Dự án & Proxy
        act_projects = Action(FluentIcon.TAG, "Quản lý Dự án / Chiến dịch", self)
        act_projects.triggered.connect(self._on_open_project_manager)
        self.settings_menu.addAction(act_projects)

        act_proxy = Action(FluentIcon.WIFI, "Công cụ Proxy & Leak Audit", self)
        act_proxy.triggered.connect(self._on_open_proxy_manager)
        self.settings_menu.addAction(act_proxy)

        act_table_cfg = Action(FluentIcon.LAYOUT, "Cài đặt bảng (28 cột MMO)", self)
        act_table_cfg.triggered.connect(self._on_table_cfg)
        self.settings_menu.addAction(act_table_cfg)

        concurrency_val = self.thread_pool.max_thread_count
        act_concurrency = Action(FluentIcon.SPEED_HIGH, f"Cấu hình luồng check ({concurrency_val} luồng)...", self)
        act_concurrency.triggered.connect(self._on_configure_concurrency)
        self.settings_menu.addAction(act_concurrency)

        self.settings_menu.addSeparator()

        # 3. Tiện ích Menu (API | Cookie, Cấp quyền, Nhận và Gửi)
        act_api_cookie = Action(FluentIcon.VPN, "API | Cookie (TikTok Direct Post)", self)
        act_api_cookie.triggered.connect(self._on_api_cookie)
        self.settings_menu.addAction(act_api_cookie)

        act_permissions = Action(FluentIcon.CERTIFICATE, "Cấp quyền (OAuth 2.0 PKCE)", self)
        act_permissions.triggered.connect(self._on_permissions)
        self.settings_menu.addAction(act_permissions)

        act_send_recv = Action(FluentIcon.SEND, "Nhận và Gửi (Sao lưu & Khôi phục CSDL)", self)
        act_send_recv.triggered.connect(self._on_send_recv)
        self.settings_menu.addAction(act_send_recv)

        self.settings_menu.addSeparator()

        # 4. Bảo trì & Trợ giúp
        act_trash = Action(FluentIcon.DELETE, "Thùng rác (Phục hồi hồ sơ)", self)
        act_trash.triggered.connect(self._on_open_trash)
        self.settings_menu.addAction(act_trash)

        act_clean = Action(FluentIcon.BRUSH, "Dọn dẹp trình duyệt & Giải phóng RAM", self)
        act_clean.triggered.connect(self._on_clean_browser)
        self.settings_menu.addAction(act_clean)

        act_guide = Action(FluentIcon.HELP, "Hướng dẫn sử dụng (Documentation)", self)
        act_guide.triggered.connect(self._on_guide)
        self.settings_menu.addAction(act_guide)

    def _show_settings_menu(self) -> None:
        """Pops up the settings menu directly below the gear button without an arrow indicator."""
        pos = self.btn_settings.mapToGlobal(QPoint(0, self.btn_settings.height() + 4))
        self.settings_menu.exec(pos)

    def _on_open_project_manager(self) -> None:
        try:
            dlg = ProjectManagerDialog(self.project_repo, self)
            dlg.exec()
            self.refresh_all_data()
        except Exception as e:
            logger.error("ProjectManagerDialog error: %s", e)
            InfoBar.error(
                title="Lỗi Quản Lý Dự Án",
                content=str(e),
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_open_proxy_manager(self) -> None:
        try:
            dlg = ProxyManagerDialog(self.proxy_repo, self.proxy_service, self)
            dlg.exec()
            self.refresh_profiles()
        except Exception as e:
            logger.error("ProxyManagerDialog error: %s", e)
            InfoBar.error(
                title="Lỗi Quản Lý Proxy",
                content=str(e),
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_add_profile(self) -> None:
        try:
            dlg = AddProfileDialog(
                profile_repo=self.profile_repo,
                project_repo=self.project_repo,
                proxy_repo=self.proxy_repo,
                vault=self.vault,
                parent=self,
            )
            if dlg.exec():
                self.refresh_profiles()
                InfoBar.success(
                    title="Hồ Sơ Mới",
                    content="Đã tạo thành công hồ sơ TikTok.",
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
        except Exception as e:
            logger.error("AddProfileDialog error: %s", e)
            InfoBar.error(
                title="Lỗi Thêm Hồ Sơ",
                content=str(e),
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_bulk_add_profiles(self) -> None:
        try:
            dlg = BulkAddProfileDialog(
                profile_repo=self.profile_repo,
                project_repo=self.project_repo,
                proxy_repo=self.proxy_repo,
                parent=self,
            )
            if dlg.exec():
                self.refresh_profiles()
        except Exception as e:
            logger.error("BulkAddProfileDialog error: %s", e)
            InfoBar.error(
                title="Lỗi Thêm Hàng Loạt",
                content=str(e),
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_show_all_profiles(self) -> None:
        self.project_combo.setCurrentIndex(0)
        self.search_profile.clear()
        self.refresh_profiles()

    def _on_sync_selected_metrics(self) -> None:
        selected_ids = self.profile_table.get_selected_profile_ids()
        if not selected_ids:
            selected_ids = [p["id"] for p in self.profile_repo.list_all()]
            if not selected_ids:
                InfoBar.warning(
                    title="Chưa có hồ sơ",
                    content="Hệ thống chưa có hồ sơ nào để đồng bộ số liệu.",
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
                return

        try:
            worker = MetricsSyncWorker(
                profile_ids=selected_ids,
                profile_service=self.profile_service,
                signal_bus=self.signal_bus,
            )
            self.thread_pool.dispatch(worker)
            InfoBar.info(
                title="Đang đồng bộ số liệu",
                content=f"Đang đồng bộ số liệu thụ động cho {len(selected_ids)} hồ sơ...",
                position=InfoBarPosition.TOP,
                parent=self,
            )
        except Exception as e:
            logger.error("Metrics sync error: %s", e)
            InfoBar.error(
                title="Lỗi Đồng Bộ",
                content=str(e),
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_launch_orbita_selected(self) -> None:
        selected = self.profile_table.get_selected_profile_ids()
        if not selected:
            InfoBar.warning(
                title="Chưa chọn hồ sơ",
                content="Vui lòng click chọn ít nhất 1 hồ sơ trong bảng để mở trình duyệt.",
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return
        self._on_launch_orbita(selected)

    def _on_launch_orbita(self, profile_id_or_ids: list[int] | int) -> None:
        target_ids = profile_id_or_ids if isinstance(profile_id_or_ids, list) else [profile_id_or_ids]
        if not target_ids:
            return

        try:
            self.daemon_supervisor.ensure_daemon_running()
        except Exception as de:
            logger.warning("Daemon supervisor check warning: %s", de)

        success_count = 0
        last_name = ""
        last_cdp = ""

        for profile_id in target_ids:
            p = self.profile_repo.get_by_id(profile_id)
            if not p:
                continue

            last_name = p.get("name", "")
            proxy = self.proxy_repo.get_by_id(p["proxy_id"]) if p.get("proxy_id") else None

            # Auto-rotate proxy if rotating proxy has change_ip_url
            if proxy and (proxy.get("proxy_type") == "rotating" or proxy.get("change_ip_url")):
                try:
                    self.proxy_service.change_rotating_ip(proxy["id"])
                except Exception as re_err:
                    logger.debug("Auto rotate proxy notice: %s", re_err)

            # Pre-launch Proxy Guard
            if proxy and not self._check_proxy_alive(proxy):
                logger.warning(
                    "Proxy for profile '%s' is unreachable (%s:%s)",
                    last_name,
                    proxy.get("host"),
                    proxy.get("port"),
                )
            try:
                uuid_val = p.get("uuid")
                debugger_addr = None
                if uuid_val:
                    try:
                        debugger_addr = self.orbita_launcher.launch_via_gologin_sdk(
                            profile_id=uuid_val,
                            proxy_data=proxy,
                            headless=False,
                            sync=False,
                        )
                    except Exception as sdk_err:
                        logger.warning(
                            "GoLogin SDK launch failed for %s, falling back to direct binary: %s", uuid_val, sdk_err
                        )

                if debugger_addr:
                    success_count += 1
                    last_cdp = debugger_addr
                else:
                    proc = self.orbita_launcher.launch_profile(p, proxy)
                    if proc and proc.pid:
                        success_count += 1
            except Exception as e:
                logger.error("Launch orbita failed for profile %d: %s", profile_id, e)

        if success_count == 1:
            content_msg = f"Đã mở trình duyệt Orbita cho hồ sơ '{last_name}'"
            if last_cdp:
                content_msg += f" (CDP: {last_cdp})."
            else:
                content_msg += "."
            InfoBar.success(
                title="Khởi Chạy Orbita",
                content=content_msg,
                position=InfoBarPosition.TOP,
                parent=self,
            )
        elif success_count > 1:
            InfoBar.success(
                title="Khởi Chạy Hàng Loạt Thành Công",
                content=f"Đã mở đồng thời {success_count} cửa sổ trình duyệt Orbita Antidetect.",
                position=InfoBarPosition.TOP,
                parent=self,
            )
        else:
            InfoBar.error(
                title="Khởi Chạy Thất Bại",
                content="Không thể mở trình duyệt cho các hồ sơ đã chọn. Vui lòng kiểm tra cấu hình.",
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_close_orbita(self, profile_ids: list[int]) -> None:
        if not profile_ids:
            return
        closed_count = 0
        for p_id in profile_ids:
            p = self.profile_repo.get_by_id(p_id)
            target = p if p else p_id
            if self.orbita_launcher.close_profile(target):
                closed_count += 1

        count = len(profile_ids)
        title = "Đóng Trình Duyệt"
        content = (
            f"Đã đóng trình duyệt cho {count} hồ sơ."
            if count > 1
            else f"Đã đóng trình duyệt cho hồ sơ #{profile_ids[0]}."
        )
        InfoBar.info(
            title=title,
            content=content,
            position=InfoBarPosition.TOP,
            parent=self,
        )

        # Passively inspect cookies and update LIVE/DIE status in background
        try:
            worker = MetricsSyncWorker(
                profile_ids=profile_ids,
                profile_service=self.profile_service,
                signal_bus=self.signal_bus,
            )
            self.thread_pool.dispatch(worker)
        except Exception as se:
            logger.debug("Passive sync dispatch on close error: %s", se)

    def _on_sync_gologin_profiles(self) -> None:
        try:
            count = self.gologin_sync_service.sync_from_local_gologin()
            self.refresh_profiles()
            InfoBar.success(
                title="Đồng Bộ GoLogin Thành Công",
                content=f"Đã đồng bộ {count} hồ sơ thực tế từ SDK GoLogin vào hệ thống.",
                position=InfoBarPosition.TOP,
                parent=self,
            )
        except Exception as e:
            logger.error("Sync GoLogin profiles error: %s", e)
            InfoBar.error(
                title="Lỗi Đồng Bộ GoLogin",
                content=str(e),
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_configure_concurrency(self) -> None:
        try:
            from PyQt6.QtWidgets import QInputDialog

            val, ok = QInputDialog.getInt(
                self,
                "Cấu Hình Luồng Check",
                "Nhập số luồng kiểm tra / tải lên đồng thời (1 - 50):",
                self.thread_pool.max_thread_count,
                1,
                50,
            )
            if ok:
                self.thread_pool.set_max_threads(val)
                self._init_settings_menu()
                InfoBar.success(
                    title="Cấu Hình Luồng",
                    content=f"Đã cập nhật số luồng chạy nền thành {val} luồng.",
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
        except Exception as e:
            logger.error("Configure concurrency error: %s", e)
            InfoBar.error(
                title="Lỗi Cấu Hình Luồng",
                content=str(e),
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_clean_browser(self) -> None:
        try:
            import os

            from src.infrastructure.browser.cache_cleaner import BrowserCacheCleaner
            from src.infrastructure.browser.process_supervisor import BrowserProcessSupervisor

            supervisor = BrowserProcessSupervisor()
            cleaner = BrowserCacheCleaner()

            # 1. Clean lingering orphan/zombie browser processes
            orphan_pids = supervisor.cleanup_orphan_browsers()

            # 2. Gather profile directories and safely purge cache
            profile_dirs: list[Path] = []
            for p in self.profile_repo.list_all():
                s_dir = p.get("storage_dir")
                if s_dir and Path(s_dir).is_dir():
                    profile_dirs.append(Path(s_dir))
                else:
                    uuid_val = p.get("uuid") or p.get("name")
                    if uuid_val:
                        candidate = Path("profiles") / str(uuid_val)
                        if candidate.is_dir():
                            profile_dirs.append(candidate)

            cache_summary = cleaner.clean_cache(profile_dirs)
            freed_cache_str = cache_summary.get("formatted_freed", "0 B")

            # 3. Trim working set RAM
            trim_res = supervisor.trim_working_set(os.getpid())
            freed_ram_mb = trim_res.get("freed_mb", 0.0)

            content = (
                f"Đã diệt {len(orphan_pids)} tiến trình mồ côi | "
                f"Giải phóng {freed_cache_str} cache rác | "
                f"Thu hồi {freed_ram_mb} MB RAM (Bảo tồn 100% Cookie)."
            )
        except Exception as e:
            logger.warning("Clean browser warning: %s", e)
            content = "Đã dọn sạch cache tạm và tối ưu bộ nhớ trình duyệt."

        InfoBar.success(
            title="Dọn Dẹp Trình Duyệt & RAM",
            content=content,
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _on_api_cookie(self) -> None:
        try:
            dlg = ApiCookieDialog(vault=self.vault, parent=self)
            dlg.exec()
        except Exception as e:
            logger.error("ApiCookieDialog error: %s", e)
            InfoBar.error(
                title="Lỗi Cấu Hình API",
                content=str(e),
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_permissions(self) -> None:
        try:
            dlg = PermissionsDialog(parent=self)
            dlg.exec()
        except Exception as e:
            logger.error("PermissionsDialog error: %s", e)
            InfoBar.error(
                title="Lỗi Cấp Quyền",
                content=str(e),
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_send_recv(self) -> None:
        try:
            dlg = SyncTransferDialog(
                project_repo=self.project_repo,
                profile_repo=self.profile_repo,
                proxy_repo=self.proxy_repo,
                parent=self,
            )
            if dlg.exec():
                self.refresh_all_data()
        except Exception as e:
            logger.error("SyncTransferDialog error: %s", e)
            InfoBar.error(
                title="Lỗi Nhận và Gửi",
                content=str(e),
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_table_cfg(self) -> None:
        try:
            dlg = TableSettingsDialog(hidden_columns=self.hidden_columns, parent=self)
            if dlg.exec():
                self.hidden_columns = dlg.hidden_columns
                for col_idx in range(self.profile_table.columnCount()):
                    self.profile_table.setColumnHidden(col_idx, col_idx in self.hidden_columns)

                # Persist to QSettings
                settings = QSettings("TAVM", "TikTokManager")
                settings.setValue("hidden_profile_columns", ",".join(str(x) for x in self.hidden_columns))

                visible_count = self.profile_table.columnCount() - len(self.hidden_columns)
                InfoBar.success(
                    title="Đã Lưu Cài Đặt Bảng",
                    content=f"Đang hiển thị {visible_count} cột, ẩn {len(self.hidden_columns)} cột.",
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
        except Exception as e:
            logger.error("TableSettingsDialog error: %s", e)
            InfoBar.error(
                title="Lỗi Cài Đặt Bảng",
                content=str(e),
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_guide(self) -> None:
        try:
            dlg = UserGuideDialog(parent=self)
            dlg.exec()
        except Exception as e:
            logger.error("UserGuideDialog error: %s", e)
            InfoBar.error(
                title="Lỗi Mở Hướng Dẫn",
                content=str(e),
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_check_single_cookie(self, profile_id_or_ids: list[int] | int) -> None:
        ids = profile_id_or_ids if isinstance(profile_id_or_ids, list) else [profile_id_or_ids]
        if not ids:
            return

        live_count = 0
        die_count = 0
        for p_id in ids:
            p = self.profile_repo.get_by_id(p_id)
            cookie = p.get("cookie") or p.get("cookies_json") if p else None
            if cookie and ("sessionid=" in cookie or "msToken=" in cookie):
                new_status = "LIVE"
                live_count += 1
            else:
                new_status = "DIE"
                die_count += 1
            self.profile_repo.update(p_id, status=new_status)

        self.refresh_profiles()
        if len(ids) == 1:
            stat = "LIVE" if live_count > 0 else "DIE"
            InfoBar.success(
                title="Kiểm Tra Cookie",
                content=f"Hồ sơ #{ids[0]}: Trạng thái hiện tại là {stat}.",
                position=InfoBarPosition.TOP,
                parent=self,
            )
        else:
            InfoBar.success(
                title="Kiểm Tra Cookie Hàng Loạt",
                content=f"Đã kiểm tra {len(ids)} hồ sơ: {live_count} LIVE, {die_count} DIE.",
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_update_profiles_proxy(self, profile_ids: list[int]) -> None:
        if not profile_ids:
            return
        try:
            dlg = AssignProxyDialog(
                profile_ids=profile_ids,
                profile_repo=self.profile_repo,
                proxy_repo=self.proxy_repo,
                parent=self,
            )
            if dlg.exec():
                self.refresh_profiles()
                InfoBar.success(
                    title="Thành Công",
                    content=f"Đã cập nhật proxy cho {len(profile_ids)} hồ sơ.",
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
        except Exception as e:
            logger.error("AssignProxyDialog error: %s", e)
            InfoBar.error(
                title="Lỗi Cập Nhật Proxy",
                content=str(e),
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _check_proxy_alive(self, proxy_data: dict[str, Any], timeout: float = 1.5) -> bool:
        """Non-blocking TCP socket check to verify proxy host and port responsiveness."""
        host = proxy_data.get("host")
        port = proxy_data.get("port")
        if not host or not port:
            return False
        import socket

        try:
            with socket.create_connection((str(host), int(port)), timeout=timeout):
                return True
        except (OSError, TimeoutError):
            return False

    def _on_remove_proxy_selected(self, profile_ids: list[int]) -> None:
        """1-click removal of both assigned proxy and WireGuard VPN configurations."""
        if not profile_ids:
            return
        self.profile_repo.bulk_update_fields(profile_ids, {"proxy_id": None, "vpn_config": None})
        self.refresh_profiles()
        count = len(profile_ids)
        msg = (
            f"Đã gỡ bỏ Proxy & WireGuard VPN cho {count} hồ sơ."
            if count > 1
            else f"Đã gỡ bỏ Proxy & WireGuard VPN cho hồ sơ #{profile_ids[0]}."
        )
        InfoBar.success(
            title="Gỡ Bỏ Cấu Hình Mạng",
            content=msg,
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _on_rotate_proxy_selected(self, profile_ids: list[int]) -> None:
        """Triggers IP rotation URL for all rotating proxies associated with selected profiles."""
        if not profile_ids:
            return
        rotated_count = 0
        for p_id in profile_ids:
            p = self.profile_repo.get_by_id(p_id)
            if not p or not p.get("proxy_id"):
                continue
            px = self.proxy_repo.get_by_id(p["proxy_id"])
            if px and (px.get("proxy_type") == "rotating" or px.get("change_ip_url")):
                try:
                    if self.proxy_service.change_rotating_ip(px["id"]):
                        rotated_count += 1
                except Exception as e:
                    logger.warning("Error rotating proxy for profile %s: %s", p_id, e)

        if rotated_count > 0:
            self.refresh_profiles()
            InfoBar.success(
                title="Xoay IP Thành Công",
                content=f"Đã xoay IP mới thành công cho {rotated_count} proxy xoay.",
                position=InfoBarPosition.TOP,
                parent=self,
            )
        else:
            InfoBar.warning(
                title="Không Có Proxy Xoay",
                content="Các hồ sơ đã chọn không sử dụng proxy xoay hoặc thiếu link đổi IP.",
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_check_proxy_selected(self, profile_ids: list[int]) -> None:
        """Dispatches non-blocking proxy health check for selected profiles."""
        if not profile_ids:
            return
        proxy_ids: set[int] = set()
        for p_id in profile_ids:
            p = self.profile_repo.get_by_id(p_id)
            if p and p.get("proxy_id"):
                proxy_ids.add(p["proxy_id"])

        if not proxy_ids:
            InfoBar.warning(
                title="Không Có Proxy",
                content="Các hồ sơ đã chọn chưa được gán proxy nào.",
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return

        from src.application.workers.proxy_check_worker import ProxyCheckWorker

        worker = ProxyCheckWorker(
            proxy_ids=list(proxy_ids),
            proxy_service=self.proxy_service,
            signal_bus=self.signal_bus,
        )
        worker.finished.connect(self.refresh_profiles)
        self.thread_pool.dispatch(worker)
        InfoBar.info(
            title="Đang Kiểm Tra Proxy",
            content=f"Đang kiểm tra kết nối cho {len(proxy_ids)} proxy...",
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _on_change_profiles_project(self, profile_ids: list[int]) -> None:
        if not profile_ids:
            return
        try:
            dlg = AssignProjectDialog(
                profile_ids=profile_ids,
                profile_repo=self.profile_repo,
                project_repo=self.project_repo,
                parent=self,
            )
            if dlg.exec():
                self.refresh_profiles()
                InfoBar.success(
                    title="Thành Công",
                    content=f"Đã chuyển {len(profile_ids)} hồ sơ vào dự án.",
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
        except Exception as e:
            logger.error("AssignProjectDialog error: %s", e)
            InfoBar.error(
                title="Lỗi Chuyển Dự Án",
                content=str(e),
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_bulk_edit_profiles(self, profile_ids: list[int]) -> None:
        if not profile_ids:
            return
        try:
            dlg = BulkEditProfileDialog(
                profile_ids=profile_ids,
                profile_repo=self.profile_repo,
                project_repo=self.project_repo,
                parent=self,
            )
            if dlg.exec():
                self.refresh_profiles()
                InfoBar.success(
                    title="Cập Nhật Thành Công",
                    content=f"Đã cập nhật thông tin hàng loạt cho {len(profile_ids)} hồ sơ.",
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
        except Exception as e:
            logger.error("BulkEditProfileDialog error: %s", e)
            InfoBar.error(
                title="Lỗi Cập Nhật Hàng Loạt",
                content=str(e),
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_edit_profile(self, profile_id: int) -> None:
        p = self.profile_repo.get_by_id(profile_id)
        if not p:
            return
        try:
            dlg = AddProfileDialog(
                profile_repo=self.profile_repo,
                project_repo=self.project_repo,
                proxy_repo=self.proxy_repo,
                vault=self.vault,
                profile_data=p,
                parent=self,
            )
            if dlg.exec():
                self.refresh_profiles()
                InfoBar.success(
                    title="Cập Nhật Hồ Sơ",
                    content=f"Đã cập nhật thông tin hồ sơ '{p.get('name')}'.",
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
        except Exception as e:
            logger.error("EditProfileDialog error: %s", e)
            InfoBar.error(
                title="Lỗi Chỉnh Sửa Hồ Sơ",
                content=str(e),
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_add_video_for_profiles(self, profile_ids: list[int]) -> None:
        if not profile_ids:
            return
        target_profile_id = profile_ids[0]
        files, _ = QFileDialog.getOpenFileNames(
            self,
            f"Chọn video nạp cho hồ sơ #{target_profile_id}",
            "",
            "Video Files (*.mp4 *.mov *.webm *.mkv)",
        )
        if not files:
            return

        added_count = 0
        for f in files:
            try:
                p = Path(f)
                vid_id = self.upload_service.enqueue_video(file_path=p, title=p.stem)
                self.video_repo.try_reserve(vid_id, target_profile_id)
                added_count += 1
            except Exception as e:
                logger.error("Error adding video for profile %s: %s", target_profile_id, e)

        self.refresh_videos()
        InfoBar.success(
            title="Đã Nạp Video Cho Hồ Sơ",
            content=f"Đã nạp {added_count} video gán cho hồ sơ #{target_profile_id}.",
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _on_open_tiktok_web(self, username: str) -> None:
        clean_user = username.strip().lstrip("@")
        if not clean_user:
            return
        url = f"https://www.tiktok.com/@{clean_user}"
        QDesktopServices.openUrl(QUrl(url))

    def _on_open_profile_folder(self, folder_or_name: str) -> None:
        folder_path = Path(folder_or_name)
        if not folder_path.is_absolute():
            base_dir = Path.home() / ".gologin" / "browser"
            folder_path = base_dir / folder_or_name

        if folder_path.exists():
            os.startfile(str(folder_path))
        else:
            InfoBar.warning(
                title="Thư Mục Không Tồn Tại",
                content=f"Chưa tìm thấy thư mục hồ sơ: {folder_path}",
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_change_profile_status(self, profile_id_or_ids: list[int] | int, status: str) -> None:
        ids = profile_id_or_ids if isinstance(profile_id_or_ids, list) else [profile_id_or_ids]
        if not ids:
            return
        self.profile_repo.bulk_update_status(ids, status=status)
        self.refresh_profiles()
        count = len(ids)
        title = "Đổi Trạng Thái"
        content = (
            f"Đã chuyển {count} hồ sơ sang trạng thái: {status}."
            if count > 1
            else f"Hồ sơ #{ids[0]} đã chuyển sang trạng thái: {status}."
        )
        InfoBar.info(
            title=title,
            content=content,
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _on_soft_delete_profiles(self, profile_ids: list[int]) -> None:
        if not profile_ids:
            return
        count = len(profile_ids)
        msg_box = MessageBox(
            "Xác Nhận Chuyển Vào Thùng Rác",
            f"Bạn có chắc chắn muốn chuyển {count} hồ sơ đã chọn vào thùng rác không?\n(Bạn có thể phục hồi hồ sơ bất kỳ lúc nào từ menu Thùng Rác).",
            self,
        )
        if not msg_box.exec():
            return

        for p_id in profile_ids:
            self.profile_repo.soft_delete(p_id)
        self.refresh_profiles()
        InfoBar.info(
            title="Thùng Rác",
            content=f"Đã chuyển {count} hồ sơ vào thùng rác.",
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _on_open_trash(self) -> None:
        try:
            dlg = TrashDialog(profile_repo=self.profile_repo, parent=self)
            dlg.exec()
            self.refresh_profiles()
        except Exception as e:
            logger.error("TrashDialog error: %s", e)
            InfoBar.error(
                title="Lỗi Thùng Rác",
                content=str(e),
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _get_initial_video_pick_folder(self) -> str:
        """Resolves default video folder from active project group if configured and exists."""
        try:
            proj_id = self.project_combo.currentData()
            if proj_id is not None:
                p = self.project_repo.get_by_id(proj_id)
                if p and p.get("video_folder"):
                    folder_path = Path(p["video_folder"])
                    if folder_path.is_dir():
                        return str(folder_path)
        except Exception as e:
            logger.debug("Failed resolving project video folder: %s", e)
        return ""

    def _on_pick_video_files(self) -> None:
        start_dir = self._get_initial_video_pick_folder()
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Chọn file video",
            start_dir,
            "Video Files (*.mp4 *.mov *.webm *.mkv)",
        )
        if not files:
            return

        added_count = 0
        for f in files:
            try:
                p = Path(f)
                self.upload_service.enqueue_video(file_path=p, title=p.stem)
                added_count += 1
            except Exception as e:
                logger.error("Error adding video %s: %s", f, e)

        self.refresh_videos()
        InfoBar.success(
            title="Đã Thêm Video",
            content=f"Đã nạp {added_count} video vào hàng đợi.",
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _on_open_batch_folder_upload(self) -> None:
        dlg = BatchFolderUploadDialog(
            profile_repo=self.profile_repo,
            upload_service=self.upload_service,
            parent=self,
        )
        if dlg.exec():
            self.refresh_videos()
            InfoBar.success(
                title="Phân Bổ Hoàn Tất",
                content=f"Đã nạp và phân bổ {len(dlg.distributed_videos)} video vào hàng đợi.",
                position=InfoBarPosition.TOP,
                parent=self,
            )
            if dlg.auto_start_upload:
                self._on_start_upload_queue()

    def _on_schedule_videos(self) -> None:
        available_videos = self.video_repo.list_available()
        if not available_videos:
            InfoBar.warning(
                title="Hàng Đợi Trống",
                content="Chưa có video nào trong hàng đợi để lên lịch.",
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return

        selected_profiles = self.profile_table.get_selected_profile_ids()
        dlg = ScheduleVideoDialog(video_count=len(available_videos), parent=self)
        if dlg.exec() and dlg.generated_schedules:
            updated_count = 0
            is_studio = getattr(dlg, "is_studio_schedule", False)
            for idx, sched_time in enumerate(dlg.generated_schedules):
                if idx < len(available_videos):
                    v = available_videos[idx]
                    target_profile = (
                        selected_profiles[idx % len(selected_profiles)]
                        if selected_profiles
                        else v.get("assigned_profile_id")
                    )
                    self.video_repo.update_schedule(
                        video_id=v["id"],
                        schedule_time=sched_time,
                        assigned_profile_id=target_profile,
                    )
                    if is_studio and target_profile:
                        # Direct TikTok Studio Native Cloud dispatch
                        worker = UploadWorker(
                            video_id=v["id"],
                            profile_id=target_profile,
                            upload_service=self.upload_service,
                            signal_bus=self.signal_bus,
                            schedule_time=sched_time,
                        )
                        self.thread_pool.dispatch(worker)
                    updated_count += 1
            self.refresh_videos()
            title_msg = "Đã Lên Lịch TikTok Studio" if is_studio else "Đã Lên Lịch Tự Động"
            content_msg = (
                f"Đã phát lệnh tải lên & lên lịch Cloud Studio cho {updated_count} video."
                if is_studio
                else f"Đã lưu lịch đăng cho {updated_count} video vào CSDL local."
            )
            InfoBar.success(
                title=title_msg,
                content=content_msg,
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_schedule_videos_from_table(self, selected_ids_or_rows: list[int]) -> None:
        if not selected_ids_or_rows:
            return

        available = self.video_repo.list_available()
        selected_profiles = self.profile_table.get_selected_profile_ids()
        dlg = ScheduleVideoDialog(video_count=len(selected_ids_or_rows), parent=self)
        if dlg.exec() and dlg.generated_schedules:
            updated_count = 0
            is_studio = getattr(dlg, "is_studio_schedule", False)
            for idx, target in enumerate(selected_ids_or_rows):
                if idx < len(dlg.generated_schedules):
                    sched_time = dlg.generated_schedules[idx]
                    target_prof = selected_profiles[idx % len(selected_profiles)] if selected_profiles else None
                    # Resolve whether target is an ID or row index
                    v = self.video_repo.get_by_id(target)
                    vid = v["id"] if v else (available[target]["id"] if target < len(available) else target)
                    self.video_repo.update_schedule(vid, schedule_time=sched_time, assigned_profile_id=target_prof)
                    if is_studio and target_prof:
                        # Direct TikTok Studio Native Cloud dispatch
                        worker = UploadWorker(
                            video_id=vid,
                            profile_id=target_prof,
                            upload_service=self.upload_service,
                            signal_bus=self.signal_bus,
                            schedule_time=sched_time,
                        )
                        self.thread_pool.dispatch(worker)
                    updated_count += 1
            self.refresh_videos()
            title_msg = "Đã Lên Lịch TikTok Studio" if is_studio else "Đã Lên Lịch Đăng"
            content_msg = (
                f"Đã phát lệnh tải lên & hẹn giờ trên Cloud Studio cho {updated_count} video đã chọn."
                if is_studio
                else f"Đã lưu lịch đăng cho {updated_count} video được chọn vào CSDL."
            )
            InfoBar.success(
                title=title_msg,
                content=content_msg,
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _check_scheduled_queue(self) -> None:
        """Periodically scans for scheduled videos that have reached their upload time."""
        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        due_videos = self.video_repo.list_scheduled_due(max_time_iso=now_iso)
        if not due_videos:
            return

        selected_profiles = self.profile_table.get_selected_profile_ids()
        dispatched = 0

        for v in due_videos:
            vid_id = v["id"]
            # Target profile: assigned profile first, or fallback to selected profiles
            target_profile = v.get("assigned_profile_id")
            if not target_profile and selected_profiles:
                target_profile = selected_profiles[dispatched % len(selected_profiles)]

            if not target_profile:
                # Cannot dispatch without an assigned or selected profile
                continue

            # Atomically reserve to prevent duplicate triggering
            reserved = self.video_repo.try_reserve(video_id=vid_id, assigned_profile_id=target_profile)
            if not reserved:
                continue

            worker = UploadWorker(
                video_id=vid_id,
                profile_id=target_profile,
                upload_service=self.upload_service,
                signal_bus=self.signal_bus,
            )
            self.thread_pool.dispatch(worker)
            dispatched += 1

        if dispatched > 0:
            logger.info("Auto-dispatch scheduler launched %d due videos", dispatched)
            self.refresh_videos()

    def _on_edit_video_metadata(self, video_id_or_row: int) -> None:
        v = self.video_repo.get_by_id(video_id_or_row)
        if not v:
            available = self.video_repo.list_available()
            if video_id_or_row < len(available):
                v = available[video_id_or_row]
        if not v:
            return

        dlg = VideoMetadataDialog(video_data=v, parent=self)
        if dlg.exec():
            new_title = dlg.video_data.get("title", "")
            self.video_repo.update_metadata(v["id"], file_name=new_title)
            self.refresh_videos()
            InfoBar.success(
                title="Cập Nhật Video",
                content=f"Đã cập nhật thông tin video: {new_title}",
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_preview_video(self, file_path: str) -> None:
        p = Path(file_path)
        if p.exists():
            try:
                os.startfile(str(p))
            except Exception as e:
                logger.error("Failed to preview video %s: %s", file_path, e)
                InfoBar.error(title="Lỗi Phát Video", content=str(e), parent=self)
        else:
            InfoBar.warning(
                title="Tệp Không Tồn Tại",
                content=f"Không tìm thấy file video: {file_path}",
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_open_video_folder(self, file_path: str) -> None:
        p = Path(file_path)
        if p.exists():
            try:
                subprocess.run(["explorer.exe", "/select,", str(p.resolve())], check=False)
            except Exception as e:
                logger.error("Failed to open Explorer for %s: %s", file_path, e)
        else:
            InfoBar.warning(
                title="Tệp Không Tồn Tại",
                content=f"Không tìm thấy file video: {file_path}",
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_open_published_link(self, link_or_id: str) -> None:
        token = link_or_id.strip()
        if not token:
            return
        if token.startswith("http://") or token.startswith("https://"):
            url = token
        else:
            url = f"https://www.tiktok.com/@user/video/{token}"
        QDesktopServices.openUrl(QUrl(url))

    def _on_start_upload_queue(self) -> None:
        selected_profiles = self.profile_table.get_selected_profile_ids()
        available_videos = self.video_repo.list_available()

        if not selected_profiles:
            InfoBar.warning(
                title="Chưa chọn hồ sơ upload",
                content="Vui lòng chọn ít nhất 1 tài khoản TikTok ở bảng trên.",
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return

        if not available_videos:
            InfoBar.warning(
                title="Hàng đợi trống",
                content="Chưa có video nào ở trạng thái sẵn sàng để đăng.",
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return

        jump_step = max(1, self.spin_jump.value() + 1)
        dispatched = 0
        for idx, video in enumerate(available_videos):
            prof_idx = (idx * jump_step) % len(selected_profiles)
            profile_id = selected_profiles[prof_idx]
            worker = UploadWorker(
                video_id=video["id"],
                profile_id=profile_id,
                upload_service=self.upload_service,
                signal_bus=self.signal_bus,
            )
            self.thread_pool.dispatch(worker)
            dispatched += 1

        InfoBar.info(
            title="Bắt Đầu Upload",
            content=f"Đã phát lệnh tải lên {dispatched} video trên QThreadPool.",
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _on_videos_dropped(self, file_paths: list[str]) -> None:
        added_count = 0
        for f in file_paths:
            try:
                p = Path(f)
                self.upload_service.enqueue_video(file_path=p, title=p.stem)
                added_count += 1
            except Exception as e:
                logger.error("Error enqueuing dropped video %s: %s", f, e)

        self.refresh_videos()
        if added_count > 0:
            InfoBar.success(
                title="Đã Kéo Thả Video",
                content=f"Đã nạp thành công {added_count} video từ Explorer vào hàng đợi.",
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_upload_progress(self, video_id: int, uploaded: int, total: int, pct: float) -> None:
        self.video_table.update_progress(video_id, pct)

    def _on_upload_completed(self, video_id: int, publish_id: str) -> None:
        # Tự động cách ly video đã upload vào thư mục _posted/
        try:
            isolated_path = self.upload_service.isolate_video_file(video_id)
            if isolated_path:
                logger.info("Video #%s physically isolated to %s", video_id, isolated_path)
        except Exception as e:
            logger.warning("Failed to physically isolate video #%s: %s", video_id, e)

        self.refresh_videos()
        InfoBar.success(
            title="Upload Hoàn Tất",
            content=f"Video #{video_id} đã xuất bản thành công & cách ly vào _posted/: {publish_id}",
            position=InfoBarPosition.TOP,
            parent=self,
        )

        # Auto-advance queue if switch is enabled
        if self.switch_auto.isChecked():
            avail = self.video_repo.list_available()
            selected = self.profile_table.get_selected_profile_ids()
            if avail and selected:
                next_video = avail[0]
                jump_step = max(1, self.spin_jump.value() + 1)
                next_profile = selected[jump_step % len(selected)]
                worker = UploadWorker(
                    video_id=next_video["id"],
                    profile_id=next_profile,
                    upload_service=self.upload_service,
                    signal_bus=self.signal_bus,
                )
                self.thread_pool.dispatch(worker)

    def _on_upload_failed(self, video_id: int, error: str) -> None:
        self.refresh_videos()
        InfoBar.error(
            title="Upload Thất Bại",
            content=f"Video #{video_id} gặp sự cố: {error}",
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _on_profile_updated(self, profile_id: int, fields: dict) -> None:
        self.refresh_profiles()

    def _on_upload_single_video(self, video_id_or_ids: list[int] | int) -> None:
        selected_profiles = self.profile_table.get_selected_profile_ids()
        if not selected_profiles:
            InfoBar.warning(
                title="Chưa chọn tài khoản",
                content="Vui lòng chọn ít nhất 1 tài khoản ở bảng trên để đăng video.",
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return

        ids = video_id_or_ids if isinstance(video_id_or_ids, list) else [video_id_or_ids]
        dispatched = 0
        for idx, target in enumerate(ids):
            v = self.video_repo.get_by_id(target)
            if not v:
                avail = self.video_repo.list_available()
                if target < len(avail):
                    v = avail[target]
            if not v:
                continue

            target_profile = selected_profiles[idx % len(selected_profiles)]
            worker = UploadWorker(
                video_id=v["id"],
                profile_id=target_profile,
                upload_service=self.upload_service,
                signal_bus=self.signal_bus,
            )
            self.thread_pool.dispatch(worker)
            dispatched += 1

        InfoBar.info(
            title="Bắt Đầu Đăng",
            content=f"Đã phát lệnh tải lên {dispatched} video trên QThreadPool.",
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _on_delete_selected_videos(self, video_ids_or_rows: list[int]) -> None:
        if not video_ids_or_rows:
            return
        count = len(video_ids_or_rows)
        msg_box = MessageBox(
            "Xác Nhận Xóa Video",
            f"Bạn có chắc chắn muốn xóa {count} video đã chọn khỏi hàng đợi không?",
            self,
        )
        if not msg_box.exec():
            return

        self.video_repo.delete_many(video_ids_or_rows)
        self.refresh_videos()
        InfoBar.info(
            title="Xóa Video",
            content=f"Đã xóa {count} video khỏi hàng đợi.",
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _on_clear_video_table(self) -> None:
        if self.video_table.rowCount() == 0:
            return
        msg_box = MessageBox(
            "Xác Nhận Xóa Bảng Video",
            "Bạn có chắc chắn muốn dọn sạch toàn bộ video đang hiển thị trong bảng không?",
            self,
        )
        if msg_box.exec():
            self.video_table.setRowCount(0)
            self.lbl_video_header.setText("Bảng video (Đã chọn 0 / 0)")
            InfoBar.info(
                title="Đã Xóa Bảng",
                content="Đã dọn sạch toàn bộ video trong bảng.",
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def closeEvent(self, event) -> None:
        """Cleanup Chromium RAM working set and shutdown daemon before closing application."""
        if self.chk_clean_exit.isChecked():
            try:
                import os

                import sammonny

                sammonny.MemoryManager.trim_process_tree_memory(os.getpid())
            except Exception:
                pass
        try:
            self.daemon_supervisor.shutdown()
        except Exception:
            pass
        event.accept()


# Parity Alias
MainWindow = TikTokManagerMainWindow
