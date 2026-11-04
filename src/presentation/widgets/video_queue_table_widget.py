"""
Video Queue Table Widget displaying video queue items with progress bars and Fluent styling.
"""

from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QTableWidgetItem,
    QWidget,
)
from qfluentwidgets import Action, FluentIcon, ProgressBar, RoundMenu, TableWidget

from src.presentation.widgets.table_helpers import (
    NumericTableWidgetItem,
    format_duration_string,
    format_mmo_metric,
    get_video_table_headers,
)


class VideoQueueTableWidget(TableWidget):
    """
    Fluent UI Table for managing video upload pipeline matching SSMATool parity.
    Supports multi-selection context operations, vector icons, and robust data persistence.
    """

    upload_now_requested = pyqtSignal(list)
    schedule_video_requested = pyqtSignal(list)
    edit_metadata_requested = pyqtSignal(int)
    preview_video_requested = pyqtSignal(str)
    open_folder_requested = pyqtSignal(str)
    open_published_link_requested = pyqtSignal(str)
    delete_video_requested = pyqtSignal(list)
    files_dropped = pyqtSignal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.headers = get_video_table_headers()
        self.setColumnCount(len(self.headers))
        self.setHorizontalHeaderLabels(self.headers)

        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setStretchLastSection(False)
        self.horizontalHeader().setFixedHeight(36)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(34)
        self.setSelectionBehavior(TableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(TableWidget.SelectionMode.ExtendedSelection)
        self.setEditTriggers(TableWidget.EditTrigger.NoEditTriggers)
        self.setWordWrap(False)
        self.setSortingEnabled(True)
        self.setSelectRightClickedRow(True)
        self.itemSelectionChanged.connect(self.updateSelectedRows)
        self.setAcceptDrops(True)
        self.setDragDropMode(TableWidget.DragDropMode.DropOnly)
        self.cellDoubleClicked.connect(self._on_cell_double_clicked)

        self._progress_bars: dict[int, ProgressBar] = {}

        # Set column widths matching UI snapshot
        self.setColumnWidth(0, 45)  # STT
        self.setColumnWidth(1, 220)  # Tiêu đề
        self.setColumnWidth(2, 80)  # Lượt view
        self.setColumnWidth(3, 80)  # Lượt like
        self.setColumnWidth(4, 75)  # Duration
        self.setColumnWidth(5, 75)  # Hiển thị
        self.setColumnWidth(6, 110)  # Lên lịch
        self.setColumnWidth(7, 120)  # Upload To
        self.setColumnWidth(8, 90)  # Tình trạng
        self.setColumnWidth(9, 130)  # Source (Progress bar)
        self.setColumnWidth(10, 150)  # Link gốc
        self.setColumnWidth(11, 120)  # ID Video
        self.setColumnWidth(12, 100)  # PVF URL
        self.setColumnWidth(13, 100)  # PAF URL

    def load_videos(self, videos: list[dict[str, Any]]) -> None:
        """Populates the table with video records."""
        self.setSortingEnabled(False)
        self.setRowCount(len(videos))
        self._progress_bars.clear()

        for row_idx, v in enumerate(videos):
            video_id = v.get("id", row_idx + 1)
            status = v.get("status", "available")

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

            # Col 0: STT (holds video dict in UserRole)
            stt_item = make_num_item(row_idx + 1, str(row_idx + 1))
            stt_item.setData(Qt.ItemDataRole.UserRole, v)
            self.setItem(row_idx, 0, stt_item)

            # Col 1: Tiêu đề
            self.setItem(row_idx, 1, make_item(v.get("file_name") or v.get("title", f"Tiêu đề {row_idx + 1}")))

            # Col 2: Lượt view
            self.setItem(
                row_idx,
                2,
                make_num_item(
                    v.get("views", 0),
                    format_mmo_metric(v.get("views", 0)),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                ),
            )

            # Col 3: Lượt like
            self.setItem(
                row_idx,
                3,
                make_num_item(
                    v.get("likes", 0),
                    format_mmo_metric(v.get("likes", 0)),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                ),
            )

            # Col 4: Duration
            duration = v.get("duration", 7.0)
            self.setItem(
                row_idx,
                4,
                make_num_item(
                    duration,
                    format_duration_string(duration),
                    Qt.AlignmentFlag.AlignCenter,
                ),
            )

            # Col 5: Hiển thị
            privacy_item = make_item("Public", Qt.AlignmentFlag.AlignCenter)
            privacy_item.setBackground(QColor("#E1DFDD"))
            self.setItem(row_idx, 5, privacy_item)

            # Col 6: Lên lịch
            sched_val = str(v.get("schedule_time") or v.get("schedule") or "")
            self.setItem(row_idx, 6, make_item(sched_val, Qt.AlignmentFlag.AlignCenter))

            # Col 7: Upload To
            target_profile_name = v.get("assigned_profile_name") or (
                f"Hồ sơ #{v['assigned_profile_id']}" if v.get("assigned_profile_id") else ""
            )
            self.setItem(row_idx, 7, make_item(target_profile_name, Qt.AlignmentFlag.AlignCenter))

            # Col 8: Tình trạng
            status_item = make_item(status.capitalize(), Qt.AlignmentFlag.AlignCenter)
            if status in ("published", "completed"):
                status_item.setForeground(QColor("#107C41"))
            elif status in ("failed", "error"):
                status_item.setForeground(QColor("#D83B01"))
            elif status in ("uploading", "reserved"):
                status_item.setForeground(QColor("#0078D4"))
            self.setItem(row_idx, 8, status_item)

            # Col 9: Source (Fluent Progress Bar)
            progress_pct = int(v.get("download_progress", 100))
            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setContentsMargins(4, 2, 4, 2)
            pbar = ProgressBar(container)
            pbar.setValue(progress_pct)
            layout.addWidget(pbar)
            self.setCellWidget(row_idx, 9, container)
            self._progress_bars[video_id] = pbar

            # Col 10: Link gốc
            self.setItem(row_idx, 10, make_item(v.get("source_url", "")))

            # Col 11: ID Video
            self.setItem(row_idx, 11, make_item(v.get("tiktok_video_id", "")))

            # Col 12: PVF URL
            self.setItem(row_idx, 12, make_item(v.get("pvf_url", "")))

            # Col 13: PAF URL
            self.setItem(row_idx, 13, make_item(v.get("paf_url", "")))

        self.setSortingEnabled(True)

    def update_progress(self, video_id: int, percentage: float) -> None:
        """Dynamically updates the Fluent ProgressBar for a specific video row."""
        if video_id in self._progress_bars:
            pbar = self._progress_bars[video_id]
            int_pct = int(min(100.0, max(0.0, percentage)))
            pbar.setValue(int_pct)

    def get_selected_videos(self) -> list[dict[str, Any]]:
        """Returns list of selected video dictionaries stored in UserRole."""
        selected_rows = sorted({index.row() for index in self.selectedIndexes()})
        videos = []
        for row in selected_rows:
            item = self.item(row, 0)
            if item:
                data = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(data, dict):
                    videos.append(data)
                    continue
            id_item = self.item(row, 11)
            vid = int(id_item.text()) if id_item and id_item.text().isdigit() else row
            videos.append({"id": vid, "row_index": row})
        return videos

    def get_selected_video_ids(self) -> list[int]:
        """Returns list of selected video database IDs."""
        videos = self.get_selected_videos()
        return [v["id"] for v in videos if "id" in v]

    def _on_cell_double_clicked(self, row: int, column: int) -> None:
        """Double clicking a video row opens the metadata edit dialog."""
        item = self.item(row, 0)
        if item:
            data = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and "id" in data:
                self.edit_metadata_requested.emit(data["id"])
                return
        id_item = self.item(row, 11)
        if id_item and id_item.text().isdigit():
            self.edit_metadata_requested.emit(int(id_item.text()))

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
            selected_ids = self.get_selected_video_ids()
            if selected_ids:
                self.delete_video_requested.emit(selected_ids)

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

        selected_videos = self.get_selected_videos()
        if not selected_videos:
            return

        selected_ids = [v["id"] for v in selected_videos if "id" in v]
        count = len(selected_videos)
        first_video = selected_videos[0]
        first_id = first_video.get("id")

        menu = RoundMenu(parent=self)

        # --- Section 1: Publishing & Scheduling ---
        upload_title = f"Đăng Ngay ({count} video đã chọn)..." if count > 1 else "Đăng Ngay Video Này"
        act_upload = Action(FluentIcon.SEND, upload_title, self)
        act_upload.triggered.connect(lambda: self.upload_now_requested.emit(selected_ids))
        menu.addAction(act_upload)

        sched_title = f"Lên Lịch Đăng ({count} video đã chọn)..." if count > 1 else "Lên Lịch Đăng Video Này..."
        act_schedule = Action(FluentIcon.CALENDAR, sched_title, self)
        act_schedule.triggered.connect(lambda: self.schedule_video_requested.emit(selected_ids))
        menu.addAction(act_schedule)

        act_edit = Action(FluentIcon.EDIT, "Chỉnh Sửa Thông Tin Video...", self)
        if first_id is not None:
            act_edit.triggered.connect(lambda: self.edit_metadata_requested.emit(int(first_id)))
        menu.addAction(act_edit)

        menu.addSeparator()

        # --- Section 2: Preview & Local File Operations ---
        file_path = str(first_video.get("file_path") or "")
        act_preview = Action(FluentIcon.PLAY, "Xem Trước Video (Play Media)", self)
        act_preview.setEnabled(bool(file_path))
        act_preview.triggered.connect(lambda: self.preview_video_requested.emit(file_path))
        menu.addAction(act_preview)

        act_folder = Action(FluentIcon.FOLDER, "Mở Thư Mục Chứa Video (Explorer)", self)
        act_folder.setEnabled(bool(file_path))
        act_folder.triggered.connect(lambda: self.open_folder_requested.emit(file_path))
        menu.addAction(act_folder)

        tiktok_vid = first_video.get("tiktok_video_id") or first_video.get("publish_id")
        act_web_vid = Action(FluentIcon.LINK, "Mở Video Đã Đăng (TikTok Web)", self)
        act_web_vid.setEnabled(bool(tiktok_vid))
        if tiktok_vid:
            act_web_vid.triggered.connect(lambda: self.open_published_link_requested.emit(str(tiktok_vid)))
        menu.addAction(act_web_vid)

        menu.addSeparator()

        # --- Section 3: Copy Information ---
        copy_menu = RoundMenu("Sao Chép Thông Tin", self)
        copy_menu.setIcon(FluentIcon.COPY)

        def copy_text(val: str) -> None:
            cb = QApplication.clipboard()
            if cb:
                cb.setText(val)

        title_val = first_video.get("file_name") or first_video.get("title", "")
        if title_val:
            act_cp_title = Action(FluentIcon.COPY, "Sao chép Tiêu Đề", self)
            act_cp_title.triggered.connect(lambda: copy_text(str(title_val)))
            copy_menu.addAction(act_cp_title)

        if file_path:
            act_cp_path = Action(FluentIcon.COPY, "Sao chép Đường Dẫn File", self)
            act_cp_path.triggered.connect(lambda: copy_text(file_path))
            copy_menu.addAction(act_cp_path)

        src_url = first_video.get("source_url") or first_video.get("pvf_url") or ""
        if src_url:
            act_cp_src = Action(FluentIcon.COPY, "Sao chép Link Nguồn / PVF", self)
            act_cp_src.triggered.connect(lambda: copy_text(str(src_url)))
            copy_menu.addAction(act_cp_src)

        if tiktok_vid:
            act_cp_tid = Action(FluentIcon.COPY, f"Sao chép ID TikTok: {tiktok_vid}", self)
            act_cp_tid.triggered.connect(lambda: copy_text(str(tiktok_vid)))
            copy_menu.addAction(act_cp_tid)

        menu.addMenu(copy_menu)

        menu.addSeparator()

        # --- Section 4: Removal ---
        del_title = f"Xóa Khỏi Hàng Đợi ({count})" if count > 1 else "Xóa Khỏi Hàng Đợi"
        act_delete = Action(FluentIcon.DELETE, del_title, self)
        act_delete.triggered.connect(lambda: self.delete_video_requested.emit(selected_ids))
        menu.addAction(act_delete)

        menu.exec(event.globalPos())

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        valid_extensions = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
        file_paths = []
        for url in urls:
            fpath = Path(url.toLocalFile())
            if fpath.is_file() and fpath.suffix.lower() in valid_extensions:
                file_paths.append(str(fpath))
            elif fpath.is_dir():
                for vf in fpath.rglob("*"):
                    if any(part in ("_posted", ".posted") for part in vf.parts):
                        continue
                    if vf.is_file() and vf.suffix.lower() in valid_extensions:
                        file_paths.append(str(vf))

        if file_paths:
            self.files_dropped.emit(file_paths)
            event.acceptProposedAction()
        else:
            event.ignore()
