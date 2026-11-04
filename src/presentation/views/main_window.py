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
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    ComboBox,
    InfoBar,
    InfoBarPosition,
    PrimaryPushButton,
    PushButton,
    SearchLineEdit,
    SpinBox,
    SwitchButton,
    Theme,
    setTheme,
)

from src.application.services.profile_service import ProfileService
from src.application.services.proxy_service import ProxyService
from src.application.services.upload_service import UploadService
from src.application.signals.app_signals import AppSignalBus
from src.application.workers.metrics_sync_worker import MetricsSyncWorker
from src.application.workers.thread_pool_manager import ThreadPoolManager
from src.application.workers.upload_worker import UploadWorker
from src.infrastructure.credentials.windows_vault import WindowsCredentialVault
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
from src.infrastructure.database.repositories.video_repository import VideoRepository
from src.infrastructure.tiktok.sammonny_adapter import SamMonnyTikTokAdapter
from src.presentation.dialogs.add_profile_dialog import AddProfileDialog
from src.presentation.dialogs.project_dialog import ProjectManagerDialog
from src.presentation.dialogs.proxy_dialog import ProxyManagerDialog
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

        # 1. Top Menu Strip
        menu_bar = QHBoxLayout()
        menu_bar.setSpacing(16)
        btn_api_cookie = PushButton("API | Cookie", self)
        btn_trash = PushButton("Thùng rác", self)
        btn_trash.clicked.connect(self._on_open_trash)
        btn_guide = PushButton("Hướng dẫn sử dụng", self)
        btn_clean_browser = PushButton("Dọn dẹp trình duyệt", self)
        btn_table_cfg = PushButton("Cài đặt bảng", self)
        btn_permissions = PushButton("Cấp quyền", self)
        btn_send_recv = PushButton("Nhận và Gửi", self)

        btn_tools = PrimaryPushButton("Công Cụ Proxy", self)
        btn_tools.clicked.connect(self._on_open_proxy_manager)

        btn_quick_find = PushButton("Tìm nhanh", self)

        for btn in (
            btn_api_cookie,
            btn_trash,
            btn_guide,
            btn_clean_browser,
            btn_table_cfg,
            btn_permissions,
            btn_send_recv,
            btn_tools,
            btn_quick_find,
        ):
            menu_bar.addWidget(btn)
        menu_bar.addStretch()
        main_layout.addLayout(menu_bar)

        # 2. Dual-Table Splitter
        self.splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.splitter.setHandleWidth(6)

        # --- Top Section: Profiles ---
        top_container = QWidget(self.splitter)
        top_layout = QVBoxLayout(top_container)
        top_layout.setContentsMargins(0, 0, 0, 4)
        top_layout.setSpacing(6)

        # Profiles Header Toolbar
        top_toolbar = QHBoxLayout()
        top_toolbar.addWidget(QLabel("Dự án:", self))

        self.project_combo = ComboBox(self)
        self.project_combo.currentIndexChanged.connect(self._on_project_changed)
        top_toolbar.addWidget(self.project_combo, 2)

        self.btn_manage_projects = PushButton("⚙ Dự án", self)
        self.btn_manage_projects.clicked.connect(self._on_open_project_manager)
        top_toolbar.addWidget(self.btn_manage_projects)

        top_toolbar.addWidget(QLabel("Luồng check:", self))
        self.spin_concurrency = SpinBox(self)
        self.spin_concurrency.setValue(10)
        self.spin_concurrency.setRange(1, 50)
        self.spin_concurrency.valueChanged.connect(self.thread_pool.set_max_threads)
        top_toolbar.addWidget(self.spin_concurrency)

        self.search_profile = SearchLineEdit(self)
        self.search_profile.setPlaceholderText("Tìm theo id|profile|email|proxy...")
        self.search_profile.textChanged.connect(self._on_search_profile)
        top_toolbar.addWidget(self.search_profile, 3)

        self.btn_add_1 = PushButton("Add 1 profile", self)
        self.btn_add_1.clicked.connect(self._on_add_profile)
        top_toolbar.addWidget(self.btn_add_1)

        self.btn_add_many = PrimaryPushButton("Add nhiều", self)
        self.btn_add_many.clicked.connect(self._on_add_profile)
        top_toolbar.addWidget(self.btn_add_many)

        self.btn_show_all = PushButton("Show all", self)
        self.btn_show_all.clicked.connect(self._on_show_all_profiles)
        top_toolbar.addWidget(self.btn_show_all)

        self.btn_sync_metrics = PushButton("🔄 Đồng bộ số liệu", self)
        self.btn_sync_metrics.clicked.connect(self._on_sync_selected_metrics)
        top_toolbar.addWidget(self.btn_sync_metrics)

        self.btn_orbita = PushButton("🌐 Mở Browser", self)
        top_toolbar.addWidget(self.btn_orbita)

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
        self.lbl_video_header.setText(f"Bảng video Đã chọn 1 / {len(available)}")

    def _on_project_changed(self) -> None:
        self.refresh_profiles()

    def _on_search_profile(self, text: str) -> None:
        # Client-side filtering across rows
        filter_text = text.strip().lower()
        for row in range(self.profile_table.rowCount()):
            matched = False
            for col in (2, 4, 6, 11):  # Name, Proxy, ID Tiktok, Email
                item = self.profile_table.item(row, col)
                if item and filter_text in item.text().lower():
                    matched = True
                    break
            self.profile_table.setRowHidden(row, not matched if filter_text else False)

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

        # Pair available videos to selected profiles
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

    def _on_open_trash(self) -> None:
        InfoBar.info(
            title="Thùng Rác",
            content="Tính năng khôi phục hồ sơ đã xóa trong CSDL SQLite.",
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _on_clear_video_table(self) -> None:
        self.video_table.setRowCount(0)
        self.lbl_video_header.setText("Bảng video Đã chọn 0 / 0")
