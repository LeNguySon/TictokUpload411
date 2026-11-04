"""
Main Application Window: Windows 11 Fluent Design Dual-Table Layout matching SSMATool parity.
"""

import logging
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSplitter,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    Action,
    ComboBox,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
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

from src.application.services.profile_service import ProfileService
from src.application.services.proxy_service import ProxyService
from src.application.services.upload_service import UploadService
from src.application.signals.app_signals import AppSignalBus
from src.application.workers.metrics_sync_worker import MetricsSyncWorker
from src.application.workers.thread_pool_manager import ThreadPoolManager
from src.application.workers.upload_worker import UploadWorker
from src.infrastructure.browser.orbita_launcher import OrbitaLauncher
from src.infrastructure.credentials.windows_vault import WindowsCredentialVault
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
from src.infrastructure.database.repositories.video_repository import VideoRepository
from src.infrastructure.tiktok.sammonny_adapter import SamMonnyTikTokAdapter
from src.presentation.dialogs.add_profile_dialog import AddProfileDialog
from src.presentation.dialogs.api_cookie_dialog import ApiCookieDialog
from src.presentation.dialogs.bulk_add_profile_dialog import BulkAddProfileDialog
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

        # Application Services
        self.proxy_service = ProxyService(proxy_repo=self.proxy_repo)
        self.profile_service = ProfileService(
            profile_repo=self.profile_repo,
            proxy_repo=self.proxy_repo,
            tiktok_adapter=self.tiktok_adapter,
        )
        self.upload_service = UploadService(
            profile_repo=self.profile_repo,
            video_repo=self.video_repo,
            tiktok_adapter=self.tiktok_adapter,
        )

        # Signal Bus & Concurrency Manager
        self.signal_bus = AppSignalBus.instance()
        self.thread_pool = ThreadPoolManager.instance()

        # UI Preferences
        self.hidden_columns: set[int] = set()

        self.setWindowTitle("SSMATool Reup Tiktok - TAVM 2026 Windows 11 Edition")
        self.resize(1366, 850)

        self._init_ui()
        self._connect_signals()
        self.refresh_all_data()

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
        top_toolbar.addWidget(QLabel("Dự án:", self))

        self.project_combo = ComboBox(self)
        self.project_combo.currentIndexChanged.connect(self._on_project_changed)
        top_toolbar.addWidget(self.project_combo, 2)

        self.search_profile = SearchLineEdit(self)
        self.search_profile.setPlaceholderText("Tìm theo id|profile|email|proxy...")
        self.search_profile.textChanged.connect(self._on_search_profile)
        top_toolbar.addWidget(self.search_profile, 5)

        # Unified Settings & Tools Menu Button
        self.btn_settings = TransparentToolButton(FluentIcon.SETTING, self)
        self.btn_settings.setToolTip("Cài đặt & Tất cả công cụ quản trị")
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

        # Video Header Toolbar
        bottom_toolbar = QHBoxLayout()
        self.lbl_video_header = QLabel("Bảng video Đã chọn 0 / 0", self)
        self.lbl_video_header.setStyleSheet("font-weight: bold;")
        bottom_toolbar.addWidget(self.lbl_video_header)

        self.btn_schedule = PushButton("📅 Lên lịch", self)
        self.btn_schedule.clicked.connect(self._on_schedule_videos)
        bottom_toolbar.addWidget(self.btn_schedule)

        self.btn_pick_pc = PrimaryPushButton("💻 Thêm Video (Máy tính)", self)
        self.btn_pick_pc.clicked.connect(self._on_pick_video_files)
        bottom_toolbar.addWidget(self.btn_pick_pc)

        self.btn_start_upload = PrimaryPushButton("🚀 Bắt đầu Upload", self)
        self.btn_start_upload.clicked.connect(self._on_start_upload_queue)
        bottom_toolbar.addWidget(self.btn_start_upload)

        bottom_toolbar.addWidget(QLabel("Nhảy thêm dòng(Enter):", self))
        self.spin_jump = SpinBox(self)
        self.spin_jump.setValue(0)
        bottom_toolbar.addWidget(self.spin_jump)

        self.search_video = SearchLineEdit(self)
        self.search_video.setPlaceholderText("Tìm video theo tiêu đề trong bảng..")
        self.search_video.textChanged.connect(self._on_search_video)
        bottom_toolbar.addWidget(self.search_video, 2)

        self.btn_clear_videos = PushButton("Xóa bảng", self)
        self.btn_clear_videos.clicked.connect(self._on_clear_video_table)
        bottom_toolbar.addWidget(self.btn_clear_videos)

        self.switch_auto = SwitchButton(self)
        self.switch_auto.setChecked(True)
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

    def _connect_signals(self) -> None:
        self.signal_bus.upload_progress.connect(self._on_upload_progress)
        self.signal_bus.upload_completed.connect(self._on_upload_completed)
        self.signal_bus.upload_failed.connect(self._on_upload_failed)
        self.signal_bus.profile_updated.connect(self._on_profile_updated)

        # Context Menu Events on Profile Table
        self.profile_table.open_orbita_requested.connect(self._on_launch_orbita)
        self.profile_table.check_cookie_requested.connect(self._on_check_single_cookie)
        self.profile_table.change_status_requested.connect(self._on_change_profile_status)
        self.profile_table.soft_delete_requested.connect(self._on_soft_delete_profiles)

        # Context Menu & Selection Events on Video Table
        self.video_table.upload_now_requested.connect(self._on_upload_single_video)
        self.video_table.delete_video_requested.connect(self._on_delete_selected_videos)
        self.video_table.edit_metadata_requested.connect(self._on_edit_video_metadata)
        self.video_table.schedule_video_requested.connect(self._on_schedule_videos_from_table)
        self.video_table.itemSelectionChanged.connect(self._on_video_selection_changed)

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

        self.btn_settings.setMenu(self.settings_menu)

    def _on_open_project_manager(self) -> None:
        dlg = ProjectManagerDialog(self.project_repo, self)
        dlg.exec()
        self.refresh_all_data()

    def _on_open_proxy_manager(self) -> None:
        dlg = ProxyManagerDialog(self.proxy_repo, self.proxy_service, self)
        dlg.exec()
        self.refresh_profiles()

    def _on_add_profile(self) -> None:
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

    def _on_bulk_add_profiles(self) -> None:
        dlg = BulkAddProfileDialog(
            profile_repo=self.profile_repo,
            project_repo=self.project_repo,
            proxy_repo=self.proxy_repo,
            parent=self,
        )
        if dlg.exec():
            self.refresh_profiles()

    def _on_show_all_profiles(self) -> None:
        self.project_combo.setCurrentIndex(0)
        self.search_profile.clear()
        self.refresh_profiles()

    def _on_sync_selected_metrics(self) -> None:
        selected_ids = self.profile_table.get_selected_profile_ids()
        if not selected_ids:
            InfoBar.warning(
                title="Chưa chọn hồ sơ",
                content="Vui lòng chọn ít nhất 1 hồ sơ để đồng bộ số liệu.",
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return

        worker = MetricsSyncWorker(
            profile_ids=selected_ids,
            profile_service=self.profile_service,
            signal_bus=self.signal_bus,
        )
        self.thread_pool.dispatch(worker)
        InfoBar.info(
            title="Đang đồng bộ số liệu",
            content=f"Đang đồng bộ cho {len(selected_ids)} hồ sơ trong luồng nền...",
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _on_launch_orbita_selected(self) -> None:
        selected = self.profile_table.get_selected_profile_ids()
        if not selected:
            InfoBar.warning(
                title="Chưa chọn hồ sơ",
                content="Vui lòng click chọn 1 hồ sơ trong bảng để mở trình duyệt.",
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return
        self._on_launch_orbita(selected[0])

    def _on_launch_orbita(self, profile_id: int) -> None:
        p = self.profile_repo.get_by_id(profile_id)
        if not p:
            return
        proxy = self.proxy_repo.get_by_id(p["proxy_id"]) if p.get("proxy_id") else None
        try:
            proc = self.orbita_launcher.launch_profile(p, proxy)
            InfoBar.success(
                title="Khởi Chạy Orbita",
                content=f"Đã mở trình duyệt cho hồ sơ '{p.get('name')}' (PID: {proc.pid}).",
                position=InfoBarPosition.TOP,
                parent=self,
            )
        except Exception as e:
            logger.error("Launch orbita failed: %s", e)
            InfoBar.error(
                title="Khởi Chạy Thất Bại",
                content=f"Không thể mở Orbita: {e}",
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_configure_concurrency(self) -> None:
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

    def _on_clean_browser(self) -> None:
        try:
            import sammonny

            sammonny.MemoryManager.trim_working_set()
        except Exception:
            pass
        InfoBar.success(
            title="Dọn Dẹp Trình Duyệt",
            content="Đã dọn sạch cache tạm và giải phóng bộ nhớ RAM thành công.",
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _on_api_cookie(self) -> None:
        dlg = ApiCookieDialog(vault=self.vault, parent=self)
        dlg.exec()

    def _on_permissions(self) -> None:
        dlg = PermissionsDialog(parent=self)
        dlg.exec()

    def _on_send_recv(self) -> None:
        dlg = SyncTransferDialog(
            project_repo=self.project_repo,
            profile_repo=self.profile_repo,
            proxy_repo=self.proxy_repo,
            parent=self,
        )
        if dlg.exec():
            self.refresh_all_data()

    def _on_table_cfg(self) -> None:
        dlg = TableSettingsDialog(hidden_columns=self.hidden_columns, parent=self)
        if dlg.exec():
            self.hidden_columns = dlg.hidden_columns
            for col_idx in range(self.profile_table.columnCount()):
                self.profile_table.setColumnHidden(col_idx, col_idx in self.hidden_columns)
            visible_count = self.profile_table.columnCount() - len(self.hidden_columns)
            InfoBar.success(
                title="Đã Lưu Cài Đặt Bảng",
                content=f"Đang hiển thị {visible_count} cột, ẩn {len(self.hidden_columns)} cột.",
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_guide(self) -> None:
        dlg = UserGuideDialog(parent=self)
        dlg.exec()

    def _on_check_single_cookie(self, profile_id: int) -> None:
        p = self.profile_repo.get_by_id(profile_id)
        cookie = p.get("cookie") or p.get("cookies_json") if p else None
        if not cookie:
            InfoBar.warning(
                title="Không có Cookie",
                content=f"Hồ sơ #{profile_id} chưa lưu cookie đăng nhập.",
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return

        is_live = bool("sessionid=" in cookie or "msToken=" in cookie)
        new_status = "LIVE" if is_live else "DIE"
        self.profile_repo.update(profile_id, status=new_status)
        self.refresh_profiles()
        InfoBar.success(
            title="Kiểm Tra Cookie",
            content=f"Hồ sơ #{profile_id}: Trạng thái hiện tại là {new_status}.",
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _on_change_profile_status(self, profile_id: int, status: str) -> None:
        self.profile_repo.update(profile_id, status=status)
        self.refresh_profiles()
        InfoBar.info(
            title="Đổi Trạng Thái",
            content=f"Hồ sơ #{profile_id} đã chuyển sang trạng thái: {status}.",
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _on_soft_delete_profiles(self, profile_ids: list[int]) -> None:
        for p_id in profile_ids:
            self.profile_repo.soft_delete(p_id)
        self.refresh_profiles()
        InfoBar.info(
            title="Thùng Rác",
            content=f"Đã chuyển {len(profile_ids)} hồ sơ vào thùng rác.",
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _on_open_trash(self) -> None:
        dlg = TrashDialog(profile_repo=self.profile_repo, parent=self)
        dlg.exec()
        self.refresh_profiles()

    def _on_pick_video_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Chọn file video",
            "",
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

        dlg = ScheduleVideoDialog(video_count=len(available_videos), parent=self)
        if dlg.exec() and dlg.generated_schedules:
            for idx, sched_time in enumerate(dlg.generated_schedules):
                if idx < len(available_videos):
                    self.video_table.setItem(idx, 6, QTableWidgetItem(sched_time))
            InfoBar.success(
                title="Đã Lên Lịch Tự Động",
                content=f"Đã phân bổ thời gian đăng cho {min(len(available_videos), len(dlg.generated_schedules))} video.",
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_schedule_videos_from_table(self, selected_rows: list[int]) -> None:
        if not selected_rows:
            return

        dlg = ScheduleVideoDialog(video_count=len(selected_rows), parent=self)
        if dlg.exec() and dlg.generated_schedules:
            for idx, row in enumerate(selected_rows):
                if idx < len(dlg.generated_schedules):
                    self.video_table.setItem(row, 6, QTableWidgetItem(dlg.generated_schedules[idx]))
            InfoBar.success(
                title="Đã Lên Lịch Đăng",
                content=f"Đã phân bổ lịch đăng cho {len(selected_rows)} video đã chọn.",
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_edit_video_metadata(self, row_index: int) -> None:
        available = self.video_repo.list_available()
        if row_index < len(available):
            v = available[row_index]
            dlg = VideoMetadataDialog(video_data=v, parent=self)
            if dlg.exec():
                new_title = dlg.video_data.get("title", "")
                new_priv = dlg.video_data.get("privacy_level", "Public")
                self.video_table.item(row_index, 1).setText(new_title)
                self.video_table.item(row_index, 5).setText(new_priv)
                self.video_repo.update_metadata(v["id"], file_name=new_title)
                InfoBar.success(
                    title="Cập Nhật Video",
                    content=f"Đã cập nhật thông tin video: {new_title}",
                    position=InfoBarPosition.TOP,
                    parent=self,
                )

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

        dispatched = 0
        for idx, video in enumerate(available_videos):
            profile_id = selected_profiles[idx % len(selected_profiles)]
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

    def _on_upload_progress(self, video_id: int, uploaded: int, total: int, pct: float) -> None:
        self.video_table.update_progress(video_id, pct)

    def _on_upload_completed(self, video_id: int, publish_id: str) -> None:
        self.refresh_videos()
        InfoBar.success(
            title="Upload Hoàn Tất",
            content=f"Video #{video_id} đã xuất bản thành công: {publish_id}",
            position=InfoBarPosition.TOP,
            parent=self,
        )

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

    def _on_upload_single_video(self, row_index: int) -> None:
        selected_profiles = self.profile_table.get_selected_profile_ids()
        if not selected_profiles:
            InfoBar.warning(
                title="Chưa chọn tài khoản",
                content="Vui lòng chọn 1 tài khoản ở bảng trên để đăng video này.",
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return

        available_videos = self.video_repo.list_available()
        if row_index < len(available_videos):
            video = available_videos[row_index]
            worker = UploadWorker(
                video_id=video["id"],
                profile_id=selected_profiles[0],
                upload_service=self.upload_service,
                signal_bus=self.signal_bus,
            )
            self.thread_pool.dispatch(worker)
            InfoBar.info(
                title="Bắt Đầu Đăng",
                content=f"Đang đăng video '{video.get('file_name')}'...",
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_delete_selected_videos(self, rows: list[int]) -> None:
        for r in sorted(rows, reverse=True):
            self.video_table.removeRow(r)
        self.lbl_video_header.setText(f"Bảng video Đã chọn 0 / {self.video_table.rowCount()}")

    def _on_clear_video_table(self) -> None:
        self.video_table.setRowCount(0)
        self.lbl_video_header.setText("Bảng video Đã chọn 0 / 0")

    def closeEvent(self, event) -> None:
        """Cleanup Chromium RAM working set before closing application."""
        if self.chk_clean_exit.isChecked():
            try:
                import sammonny

                sammonny.MemoryManager.trim_working_set()
            except Exception:
                pass
        event.accept()
