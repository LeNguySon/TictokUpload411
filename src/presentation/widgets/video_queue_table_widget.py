"""
Video Queue Table Widget displaying video queue items with progress bars and Fluent styling.
"""

from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QHBoxLayout, QHeaderView, QTableWidgetItem, QWidget
from qfluentwidgets import Action, ProgressBar, RoundMenu, TableWidget

from src.presentation.widgets.table_helpers import (
    format_duration_string,
    format_mmo_metric,
    get_video_table_headers,
)


class VideoQueueTableWidget(TableWidget):
    """
    Fluent UI Table for managing video upload pipeline matching SSMATool parity.
    """

    upload_now_requested = pyqtSignal(int)
    delete_video_requested = pyqtSignal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.headers = get_video_table_headers()
        self.setColumnCount(len(self.headers))
        self.setHorizontalHeaderLabels(self.headers)

        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setStretchLastSection(False)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(TableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(TableWidget.SelectionMode.ExtendedSelection)
        self.setWordWrap(False)
        self.setSortingEnabled(True)

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
                return item

            # Col 0: STT
            self.setItem(row_idx, 0, make_item(str(row_idx + 1), Qt.AlignmentFlag.AlignCenter))

            # Col 1: Tiêu đề
            self.setItem(row_idx, 1, make_item(v.get("file_name") or v.get("title", f"Tiêu đề {row_idx + 1}")))

            # Col 2: Lượt view
            self.setItem(
                row_idx,
                2,
                make_item(
                    format_mmo_metric(v.get("views", 0)), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                ),
            )

            # Col 3: Lượt like
            self.setItem(
                row_idx,
                3,
                make_item(
                    format_mmo_metric(v.get("likes", 0)), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                ),
            )

            # Col 4: Duration
            duration = v.get("duration", 7.0)
            self.setItem(row_idx, 4, make_item(format_duration_string(duration), Qt.AlignmentFlag.AlignCenter))

            # Col 5: Hiển thị
            privacy_item = make_item("Public", Qt.AlignmentFlag.AlignCenter)
            privacy_item.setBackground(QColor("#E1DFDD"))
            self.setItem(row_idx, 5, privacy_item)

            # Col 6: Lên lịch
            self.setItem(row_idx, 6, make_item(v.get("schedule", ""), Qt.AlignmentFlag.AlignCenter))

            # Col 7: Upload To
            self.setItem(row_idx, 7, make_item(v.get("assigned_profile_name", ""), Qt.AlignmentFlag.AlignCenter))

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
            pbar.setValMode(ProgressBar.ValMode.CUSTOM)
            pbar.setCustomText(f"{progress_pct}%")
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
            pbar.setCustomText(f"{int_pct}%")

    def get_selected_video_ids(self) -> list[int]:
        """Returns list of selected video IDs."""
        selected_rows = {index.row() for index in self.selectedIndexes()}
        return list(selected_rows)

    def contextMenuEvent(self, event) -> None:
        selected_rows = self.get_selected_video_ids()
        if not selected_rows:
            return

        menu = RoundMenu(parent=self)

        act_upload = Action("🚀 Đăng Ngay Video Này", self)
        act_upload.triggered.connect(lambda: self.upload_now_requested.emit(selected_rows[0]))
        menu.addAction(act_upload)

        menu.addSeparator()

        act_delete = Action("🗑 Xóa Khỏi Bảng", self)
        act_delete.triggered.connect(lambda: self.delete_video_requested.emit(selected_rows))
        menu.addAction(act_delete)

        menu.exec(event.globalPos())
