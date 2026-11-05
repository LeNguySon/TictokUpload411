"""
Video Upload Log Widget displaying per-video real-time execution logs and multi-threaded progress.
Supports per-video filtering, auto-scroll, AgentShield secret redaction, and Fluent styling.
"""

import html
import re
from collections import deque
from typing import Any

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    ComboBox,
    FluentIcon,
    TransparentToolButton,
)

# AgentShield regex patterns for redacting sensitive authentication secrets
_SENSITIVE_PATTERNS = [
    re.compile(r"(sessionid[=:]\s*)([a-zA-Z0-9_-]{10,})", re.IGNORECASE),
    re.compile(r"(act\.[a-zA-Z0-9_\-\.]{10,})", re.IGNORECASE),
    re.compile(r"(bearer\s+)([a-zA-Z0-9_\-\.]{15,})", re.IGNORECASE),
    re.compile(r"(access_token[=:]\s*[\"']?)([a-zA-Z0-9_\-\.]{15,})", re.IGNORECASE),
    re.compile(r"(csrf_token[=:]\s*[\"']?)([a-zA-Z0-9_\-\.]{10,})", re.IGNORECASE),
    re.compile(r"(cookie:\s*)([^\r\n]{20,})", re.IGNORECASE),
]


def redact_sensitive_text(text: str) -> str:
    """Masks authentication cookies, tokens, and session secrets according to AgentShield."""
    redacted = str(text)
    for pat in _SENSITIVE_PATTERNS:
        # If group has prefix, preserve prefix and mask payload
        if pat.groups == 2:
            redacted = pat.sub(r"\1[REDACTED]", redacted)
        else:
            redacted = pat.sub(r"[REDACTED]", redacted)
    return redacted


class VideoUploadLogWidget(QWidget):
    """
    Enterprise Realtime Upload Monitor & Log Console for concurrent video publishing.
    Tracks granular step logs and progress per video without UI starvation.
    """

    toggle_collapse_requested = pyqtSignal()
    MAX_LINES_PER_VIDEO = 500
    MAX_ALL_LINES = 2000

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._logs_by_video: dict[int, deque[dict[str, Any]]] = {}
        self._all_logs: deque[dict[str, Any]] = deque(maxlen=self.MAX_ALL_LINES)
        self._selected_video_id: int | None = None
        self._video_stages: dict[int, str] = {}
        self._video_titles: dict[int, str] = {}
        self._active_count = 0
        self._success_count = 0
        self._failed_count = 0

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        # 1. Header Toolbar
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        lbl_title = QLabel("⚡ Nhật Ký Upload Đa Luồng:", self)
        lbl_title.setStyleSheet("font-weight: bold; font-size: 12px; color: #323130;")
        header_layout.addWidget(lbl_title)

        # Video Filter Dropdown
        self.combo_video_filter = ComboBox(self)
        self.combo_video_filter.setFixedHeight(28)
        self.combo_video_filter.setMinimumWidth(240)
        self.combo_video_filter.addItem("Tất cả video (Tổng hợp)", userData=None)
        self.combo_video_filter.currentIndexChanged.connect(self._on_filter_changed)
        header_layout.addWidget(self.combo_video_filter)

        # Status counts badge
        self.lbl_counts = QLabel("Đang tải: 0 | Thành công: 0 | Lỗi: 0", self)
        self.lbl_counts.setStyleSheet(
            "color: #605E5C; font-size: 11px; padding: 2px 6px; background: #F3F2F1; border-radius: 4px;"
        )
        header_layout.addWidget(self.lbl_counts)

        header_layout.addStretch()

        # Auto-scroll checkbox
        self.chk_autoscroll = QCheckBox("Tự cuộn", self)
        self.chk_autoscroll.setChecked(True)
        self.chk_autoscroll.setStyleSheet("font-size: 11px; color: #605E5C;")
        header_layout.addWidget(self.chk_autoscroll)

        # Clear button
        self.btn_clear = TransparentToolButton(FluentIcon.DELETE, self)
        self.btn_clear.setFixedSize(28, 28)
        self.btn_clear.setToolTip("Dọn sạch nhật ký")
        self.btn_clear.clicked.connect(self.clear_logs)
        header_layout.addWidget(self.btn_clear)

        # Export button
        self.btn_export = TransparentToolButton(FluentIcon.DOWNLOAD, self)
        self.btn_export.setFixedSize(28, 28)
        self.btn_export.setToolTip("Xuất nhật ký ra file text")
        self.btn_export.clicked.connect(self._on_export_logs)
        header_layout.addWidget(self.btn_export)

        # Collapse / Hide button
        self.btn_collapse = TransparentToolButton(FluentIcon.MINIMIZE, self)
        self.btn_collapse.setFixedSize(28, 28)
        self.btn_collapse.setToolTip("Thu gọn / Mở rộng bảng nhật ký")
        self.btn_collapse.clicked.connect(self.toggle_collapse_requested.emit)
        header_layout.addWidget(self.btn_collapse)

        layout.addLayout(header_layout)

        # 2. Log Display Text Area
        self.text_browser = QTextBrowser(self)
        self.text_browser.setOpenExternalLinks(False)
        self.text_browser.setFont(QFont("Consolas", 10))
        self.text_browser.setStyleSheet(
            """
            QTextBrowser {
                background-color: #1E1E1E;
                color: #D4D4D4;
                border: 1px solid #3C3C3C;
                border-radius: 6px;
                padding: 6px;
                selection-background-color: #264F78;
            }
            """
        )
        layout.addWidget(self.text_browser, 1)

    def append_log(
        self,
        video_id: int,
        timestamp: str,
        stage: str,
        message: str,
        level: str = "INFO",
        title: str | None = None,
    ) -> None:
        """Appends a new log entry for a specific video and updates display."""
        safe_message = redact_sensitive_text(message)

        if title and video_id not in self._video_titles:
            self._video_titles[video_id] = title

        entry = {
            "video_id": video_id,
            "timestamp": timestamp,
            "stage": stage.upper(),
            "message": safe_message,
            "level": level.upper(),
            "title": self._video_titles.get(video_id, f"Video #{video_id}"),
        }

        if video_id not in self._logs_by_video:
            self._logs_by_video[video_id] = deque(maxlen=self.MAX_LINES_PER_VIDEO)
            # Add to dropdown if not present
            self._add_video_to_combo(video_id)

        self._logs_by_video[video_id].append(entry)
        self._all_logs.append(entry)

        # Update metrics counters
        if entry["stage"] in ("START", "INIT"):
            self._active_count += 1
        elif entry["stage"] in ("SUCCESS", "COMPLETED"):
            self._active_count = max(0, self._active_count - 1)
            self._success_count += 1
        elif entry["stage"] in ("ERROR", "FAIL", "FAILED"):
            self._active_count = max(0, self._active_count - 1)
            self._failed_count += 1
        self._update_counts_badge()

        # Render to UI if currently matching the filter
        if self._selected_video_id is None or self._selected_video_id == video_id:
            self._append_rendered_line(entry)

    def update_stage(self, video_id: int, stage_text: str) -> None:
        """Updates internal status stage for given video."""
        self._video_stages[video_id] = stage_text
        self._refresh_combo_text(video_id)

    def filter_by_video(self, video_id: int | None) -> None:
        """Sets current filter to a specific video ID or None for all."""
        self._selected_video_id = video_id
        # Sync dropdown index
        for idx in range(self.combo_video_filter.count()):
            if self.combo_video_filter.itemData(idx) == video_id:
                if self.combo_video_filter.currentIndex() != idx:
                    self.combo_video_filter.setCurrentIndex(idx)
                break
        self._render_current_view()

    def focus_video(self, video_id: int) -> None:
        """Public slot to switch filter directly to given video ID."""
        if video_id not in self._logs_by_video:
            self._logs_by_video[video_id] = deque(maxlen=self.MAX_LINES_PER_VIDEO)
            self._add_video_to_combo(video_id)
        self.filter_by_video(video_id)

    def get_logs_for_video(self, video_id: int) -> list[dict[str, Any]]:
        """Returns recorded logs for a given video ID."""
        return list(self._logs_by_video.get(video_id, []))

    def get_all_logs(self) -> list[dict[str, Any]]:
        """Returns all aggregated logs."""
        return list(self._all_logs)

    def get_displayed_plain_text(self) -> str:
        """Returns plain text currently shown in the browser."""
        return self.text_browser.toPlainText()

    def clear_logs(self, video_id: int | None = None) -> None:
        """Clears logs for a specific video or all."""
        if video_id is not None:
            if video_id in self._logs_by_video:
                self._logs_by_video[video_id].clear()
        else:
            self._logs_by_video.clear()
            self._all_logs.clear()
            self._active_count = 0
            self._success_count = 0
            self._failed_count = 0
            self._update_counts_badge()
            # Reset combo keeping only 'All'
            while self.combo_video_filter.count() > 1:
                self.combo_video_filter.removeItem(1)

        self.text_browser.clear()

    def _on_filter_changed(self, index: int) -> None:
        vid = self.combo_video_filter.itemData(index)
        self._selected_video_id = vid
        self._render_current_view()

    def _render_current_view(self) -> None:
        self.text_browser.clear()
        entries = (
            self.get_logs_for_video(self._selected_video_id)
            if self._selected_video_id is not None
            else self.get_all_logs()
        )
        for e in entries:
            self._append_rendered_line(e)

    def _append_rendered_line(self, entry: dict[str, Any]) -> None:
        ts = html.escape(entry.get("timestamp", ""))
        stage = html.escape(entry.get("stage", ""))
        msg = html.escape(entry.get("message", ""))
        vid = entry.get("video_id", 0)

        # Color palette for stages
        color_map = {
            "START": "#0098FF",
            "INIT": "#0098FF",
            "RESERVE": "#3399FF",
            "PROFILE": "#B180F0",
            "TOKEN": "#B180F0",
            "CHUNK": "#00C7B7",
            "UPLOAD": "#00C7B7",
            "STREAM": "#00C7B7",
            "PUBLISH": "#FFAA44",
            "ISOLATE": "#80D820",
            "SUCCESS": "#47D070",
            "COMPLETED": "#47D070",
            "ERROR": "#FF5252",
            "FAIL": "#FF5252",
            "FAILED": "#FF5252",
        }
        badge_color = color_map.get(stage, "#CCCCCC")

        # In aggregated mode, prefix with video tag
        vid_prefix = (
            f"<span style='color: #E2B714; font-weight: bold;'>[Video #{vid}]</span> "
            if self._selected_video_id is None
            else ""
        )

        html_line = (
            f"<div style='line-height: 140%; margin-bottom: 2px;'>"
            f"<span style='color: #7A7A7A;'>[{ts}]</span> "
            f"{vid_prefix}"
            f"<span style='color: {badge_color}; font-weight: bold;'>[{stage}]</span> "
            f"<span style='color: #E6E6E6;'>{msg}</span>"
            f"</div>"
        )

        cursor = self.text_browser.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.text_browser.setTextCursor(cursor)
        self.text_browser.insertHtml(html_line)

        if self.chk_autoscroll.isChecked():
            self.text_browser.moveCursor(QTextCursor.MoveOperation.End)

    def _add_video_to_combo(self, video_id: int) -> None:
        title = self._video_titles.get(video_id, f"Video #{video_id}")
        display_text = f"#{video_id} - {title[:20]}"
        self.combo_video_filter.addItem(display_text, userData=video_id)

    def _refresh_combo_text(self, video_id: int) -> None:
        stage = self._video_stages.get(video_id, "")
        for idx in range(1, self.combo_video_filter.count()):
            if self.combo_video_filter.itemData(idx) == video_id:
                title = self._video_titles.get(video_id, f"Video #{video_id}")
                suffix = f" ({stage})" if stage else ""
                self.combo_video_filter.setItemText(idx, f"#{video_id} - {title[:18]}{suffix}")
                break

    def _update_counts_badge(self) -> None:
        self.lbl_counts.setText(
            f"Đang tải: {self._active_count} | Thành công: {self._success_count} | Lỗi: {self._failed_count}"
        )

    def _on_export_logs(self) -> None:
        text = self.text_browser.toPlainText()
        if not text:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Xuất Nhật Ký Upload", "upload_logs.txt", "Text Files (*.txt);;All Files (*)"
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
