"""
Video Queue Table Widget displaying video queue items with progress bars and Fluent styling.
"""

from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QApplication,
    QHeaderView,
    QTableWidgetItem,
)
from qfluentwidgets import Action, FluentIcon, RoundMenu

from src.application.workers.task_worker import run_task
from src.presentation.delegates.progress_bar_delegate import PROGRESS_ROLE, ProgressBarDelegate
from src.presentation.widgets.fast_table import FastTableWidget, RowIndex
from src.presentation.widgets.table_helpers import (
    NumericTableWidgetItem,
    format_duration_string,
    format_mmo_metric,
    get_video_table_headers,
)

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


def collect_video_files(paths: list[str]) -> list[str]:
    """Expands dropped files/folders into video files, skipping already-posted folders."""
    found: list[str] = []
    for raw in paths:
        fpath = Path(raw)
        if fpath.is_file() and fpath.suffix.lower() in VIDEO_EXTENSIONS:
            found.append(str(fpath))
        elif fpath.is_dir():
            for vf in fpath.rglob("*"):
                if any(part in ("_posted", ".posted") for part in vf.parts):
                    continue
                if vf.is_file() and vf.suffix.lower() in VIDEO_EXTENSIONS:
                    found.append(str(vf))
    return found


def _clamp_pct(value: object) -> int:
    try:
        return int(min(100.0, max(0.0, float(value))))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


class VideoQueueTableWidget(FastTableWidget):
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
    view_upload_logs_requested = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._video_rows = RowIndex()
        self.headers = get_video_table_headers()
        self.setColumnCount(len(self.headers))
        self.setHorizontalHeaderLabels(self.headers)

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
        self.setAcceptDrops(True)
        self.setDragDropMode(FastTableWidget.DragDropMode.DropOnly)
        self.cellDoubleClicked.connect(self._on_cell_double_clicked)

        self.setItemDelegateForColumn(10, ProgressBarDelegate(self))
        self._video_logs: dict[int, list[str]] = {}

        # Set column widths matching UI snapshot
        self.setColumnWidth(0, 45)  # STT
        self.setColumnWidth(1, 200)  # Tiêu đề
        self.setColumnWidth(2, 110)  # Dự Án
        self.setColumnWidth(3, 80)  # Lượt view
        self.setColumnWidth(4, 80)  # Lượt like
        self.setColumnWidth(5, 75)  # Duration
        self.setColumnWidth(6, 75)  # Hiển thị
        self.setColumnWidth(7, 110)  # Lên lịch
        self.setColumnWidth(8, 120)  # Upload To
        self.setColumnWidth(9, 90)  # Tình trạng
        self.setColumnWidth(10, 120)  # Tiến trình (Progress bar)
        self.setColumnWidth(11, 240)  # Nhật Ký Upload (Step logs & Error text)
        self.setColumnWidth(12, 150)  # Link gốc
        self.setColumnWidth(13, 120)  # ID Video
        self.setColumnWidth(14, 100)  # PVF URL
        self.setColumnWidth(15, 100)  # PAF URL

    def load_videos(self, videos: list[dict[str, Any]]) -> None:
        """Populates the table with video records (repaint suspended while filling)."""
        self.setUpdatesEnabled(False)
        try:
            self._fill_videos(videos)
        finally:
            self.setUpdatesEnabled(True)
            self.setSortingEnabled(True)

    def _fill_videos(self, videos: list[dict[str, Any]]) -> None:
        self.setSortingEnabled(False)
        self.clearSelection()
        self._video_rows.clear()
        self.setRowCount(len(videos))

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
            self._video_rows.add(video_id, stt_item)

            # Col 1: Tiêu đề
            self.setItem(row_idx, 1, make_item(v.get("file_name") or v.get("title", f"Tiêu đề {row_idx + 1}")))

            # Col 2: Dự Án
            proj_name = v.get("project_name")
            if not proj_name and v.get("file_path"):
                try:
                    proj_name = Path(v["file_path"]).parent.name
                except Exception:
                    proj_name = ""
            if not proj_name:
                proj_name = "Chung"
            self.setItem(row_idx, 2, make_item(proj_name, Qt.AlignmentFlag.AlignCenter))

            # Col 3: Lượt view
            self.setItem(
                row_idx,
                3,
                make_num_item(
                    v.get("views", 0),
                    format_mmo_metric(v.get("views", 0)),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                ),
            )

            # Col 4: Lượt like
            self.setItem(
                row_idx,
                4,
                make_num_item(
                    v.get("likes", 0),
                    format_mmo_metric(v.get("likes", 0)),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                ),
            )

            # Col 5: Duration
            duration = v.get("duration", 7.0)
            self.setItem(
                row_idx,
                5,
                make_num_item(
                    duration,
                    format_duration_string(duration),
                    Qt.AlignmentFlag.AlignCenter,
                ),
            )

            # Col 6: Hiển thị
            privacy_item = make_item("Public", Qt.AlignmentFlag.AlignCenter)
            privacy_item.setBackground(QColor("#E1DFDD"))
            self.setItem(row_idx, 6, privacy_item)

            # Col 7: Lên lịch
            sched_val = str(v.get("schedule_time") or v.get("schedule") or "")
            self.setItem(row_idx, 7, make_item(sched_val, Qt.AlignmentFlag.AlignCenter))

            # Col 8: Upload To
            target_profile_name = v.get("assigned_profile_name") or (
                f"Hồ sơ #{v['assigned_profile_id']}" if v.get("assigned_profile_id") else ""
            )
            self.setItem(row_idx, 8, make_item(target_profile_name, Qt.AlignmentFlag.AlignCenter))

            # Col 9: Tình trạng
            status_item = make_item(status.capitalize(), Qt.AlignmentFlag.AlignCenter)
            if status in ("published", "completed"):
                status_item.setForeground(QColor("#107C41"))
            elif status in ("failed", "error"):
                status_item.setForeground(QColor("#D83B01"))
            elif status in ("uploading", "reserved"):
                status_item.setForeground(QColor("#0078D4"))
            self.setItem(row_idx, 9, status_item)

            # Col 10: Tiến trình — painted by ProgressBarDelegate from UserRole (no per-row widget)
            progress_item = QTableWidgetItem()
            progress_item.setData(PROGRESS_ROLE, _clamp_pct(v.get("download_progress", 100)))
            progress_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.setItem(row_idx, 10, progress_item)

            # Col 11: Nhật Ký Upload
            log_text = v.get("error_message") or "-"
            log_item = make_item(log_text)
            if v.get("error_message"):
                log_item.setText(f"❌ Lỗi: {v['error_message']}")
                log_item.setForeground(QColor("#D83B01"))
                log_item.setToolTip(v["error_message"])
            self.setItem(row_idx, 11, log_item)

            # Col 12: Link gốc
            self.setItem(row_idx, 12, make_item(v.get("source_url", "")))

            # Col 13: ID Video
            self.setItem(row_idx, 13, make_item(v.get("tiktok_video_id", "")))

            # Col 14: PVF URL
            self.setItem(row_idx, 14, make_item(v.get("pvf_url", "")))

            # Col 15: PAF URL
            self.setItem(row_idx, 15, make_item(v.get("paf_url", "")))

    def progress_value(self, video_id: int) -> int | None:
        """Current progress (0-100) shown for a video, or None if the video is not in the table."""
        row = self.find_row_by_video_id(video_id)
        item = self.item(row, 10) if row is not None else None
        return None if item is None else item.data(PROGRESS_ROLE)

    def find_row_by_video_id(self, video_id: int) -> int | None:
        """O(1) lookup of the current table row for a video ID (correct after sorting)."""
        return self._video_rows.row(self, video_id)

    def append_log(
        self,
        video_id: int,
        timestamp: str,
        stage: str,
        message: str,
        level: str = "INFO",
    ) -> None:
        """Appends log entry into the dedicated 'Nhật Ký Upload' column (Col 11) for the video."""
        if video_id not in self._video_logs:
            self._video_logs[video_id] = []
        log_line = f"[{timestamp}] [{stage}] {message}"
        self._video_logs[video_id].append(log_line)

        row = self.find_row_by_video_id(video_id)
        if row is None:
            return

        item = self.item(row, 11)
        if not item:
            item = QTableWidgetItem()
            self.setItem(row, 11, item)

        display_text = f"[{stage}] {message}"
        item.setText(display_text)
        item.setToolTip("\n".join(self._video_logs[video_id][-10:]))

        stage_up = stage.upper()
        if stage_up in ("SUCCESS", "COMPLETED"):
            item.setForeground(QColor("#107C41"))
            self.update_stage(video_id, "Hoàn tất")
        elif stage_up in ("ERROR", "FAIL", "FAILED"):
            item.setText(f"❌ Lỗi: {message}")
            item.setForeground(QColor("#D83B01"))
            self.update_stage(video_id, "Thất bại")
        elif stage_up in ("CHUNK", "STREAM", "UPLOAD"):
            item.setForeground(QColor("#0078D4"))
        elif stage_up in ("START", "INIT", "RESERVE"):
            item.setForeground(QColor("#5C2D91"))

    def set_video_error(self, video_id: int, error_message: str) -> None:
        """Displays error directly in Col 11 and marks status failed in Col 9."""
        if video_id not in self._video_logs:
            self._video_logs[video_id] = []
        self._video_logs[video_id].append(f"[ERROR] {error_message}")

        row = self.find_row_by_video_id(video_id)
        if row is not None:
            item = self.item(row, 11)
            if not item:
                item = QTableWidgetItem()
                self.setItem(row, 11, item)
            item.setText(f"❌ Lỗi: {error_message}")
            item.setForeground(QColor("#D83B01"))
            item.setToolTip("\n".join(self._video_logs[video_id]))

        self.update_stage(video_id, "Thất bại")

    def update_stage(self, video_id: int, stage_text: str) -> None:
        """Updates the status column (Col 9) with detailed stage text and color."""
        row = self.find_row_by_video_id(video_id)
        if row is None:
            return
        status_item = self.item(row, 9)
        if not status_item:
            status_item = QTableWidgetItem(stage_text)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setItem(row, 9, status_item)
        else:
            status_item.setText(stage_text)

        lower_stage = stage_text.lower()
        if any(w in lower_stage for w in ("hoàn tất", "thành công", "completed", "published")):
            status_item.setForeground(QColor("#107C41"))
        elif any(w in lower_stage for w in ("lỗi", "thất bại", "error", "fail")):
            status_item.setForeground(QColor("#D83B01"))
        elif any(w in lower_stage for w in ("đang", "khởi tạo", "tải", "upload", "chunk", "publish")):
            status_item.setForeground(QColor("#0078D4"))

    def update_progress(self, video_id: int, percentage: float, speed_text: str = "") -> None:
        """Updates the progress cell (repaints only that cell) and the status text for a video row."""
        row = self.find_row_by_video_id(video_id)
        if row is not None:
            progress_item = self.item(row, 10)
            if progress_item is not None:
                progress_item.setData(PROGRESS_ROLE, _clamp_pct(percentage))
            status_item = self.item(row, 9)
            if status_item:
                current_text = status_item.text().lower()
                if not any(k in current_text for k in ("hoàn tất", "thành công", "lỗi", "thất bại")):
                    int_pct = int(min(100.0, max(0.0, percentage)))
                    extra = f" ({speed_text})" if speed_text else ""
                    status_item.setText(f"Đang tải {int_pct}%{extra}")
                    status_item.setForeground(QColor("#0078D4"))

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
            id_item = self.item(row, 13)
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
        id_item = self.item(row, 13)
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

        if first_id is not None:
            act_logs = Action(FluentIcon.DOCUMENT, "Xem Nhật Ký Upload (Logs)...", self)
            act_logs.triggered.connect(lambda: self.view_upload_logs_requested.emit(int(first_id)))
            menu.addAction(act_logs)

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
        """Accepts dropped files/folders at once; recursive folder scanning runs off the GUI thread (T7)."""
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        run_task(lambda: collect_video_files(paths), on_result=self._emit_dropped_files)

    def _emit_dropped_files(self, file_paths: list[str]) -> None:
        if file_paths:
            try:
                self.files_dropped.emit(file_paths)
            except RuntimeError:  # table destroyed while scanning
                pass
