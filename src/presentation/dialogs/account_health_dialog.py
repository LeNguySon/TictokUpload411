"""
AccountHealthDialog — Giao diện Kiểm tra Chất lượng Tài khoản, Gậy Vi phạm & Gậy Nguyên tác TikTok.
Bổ sung:
- Kháng cáo Video Vi phạm / Gậy Nguyên tác (Video Appeal)
- Kiểm tra Tiến độ Kháng cáo (Check Appeals)
- Đếm ngược & Nộp lại Đơn Quỹ Nhà Sáng Tạo (Creator Rewards Re-application)
- Tích hợp GoLogin SDK & Proxy Routing
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from PyQt6 import sip
from PyQt6.QtGui import QCloseEvent, QColor
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import FluentIcon, InfoBar, InfoBarPosition, PrimaryPushButton, PushButton

from src.application.workers.task_worker import run_task
from src.infrastructure.database.connection import db_session
from src.infrastructure.tiktok.moderation_service import TikTokModerationService
from src.presentation.dialogs.dialog_helpers import (
    STANDARD_DIALOG_MARGINS,
    STANDARD_DIALOG_SPACING,
    create_dialog_header,
    status_color,
    style_card,
    style_plain_table,
    style_tab_widget,
)
from src.presentation.widgets.table_helpers import h_header, v_header

logger = logging.getLogger(__name__)


def fetch_health_data(db_path: Path | str, profile_id: int) -> dict[str, Any] | None:
    """Reads the profile, its violated videos and its appeals. Pure DB read: runs on any thread."""
    with db_session(db_path, write=False) as conn:
        profile = conn.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
        if not profile:
            return None
        violations = conn.execute(
            "SELECT * FROM violateVideos WHERE profile_id=? ORDER BY id DESC", (profile_id,)
        ).fetchall()
        appeals = conn.execute(
            "SELECT * FROM accountAppeals WHERE profile_id=? ORDER BY id DESC", (profile_id,)
        ).fetchall()
        deep_rows = conn.execute(
            """
            SELECT video_id, title, views, likes, comments, search_terms_json,
                   traffic_sources_json, retention_points_json, finish_rate, ai_comments_json
            FROM videoTables
            WHERE profile_id=? AND (search_terms_json IS NOT NULL OR traffic_sources_json IS NOT NULL)
            ORDER BY views DESC, id DESC LIMIT 25;
            """,
            (profile_id,),
        ).fetchall()
        return {
            "profile": dict(profile),
            "violations": [dict(v) for v in violations],
            "appeals": [dict(a) for a in appeals],
            "deep_analytics": [dict(d) for d in deep_rows],
        }


# getPenaltyDetails sends penalties[0].date = the day TikTok penalized the video; it sends no appeal deadline.
VIOLATION_COLUMNS = ["Video ID", "Tiêu đề video", "Loại gậy vi phạm", "Ngày bị xử phạt", "Trạng thái"]

_VIOLATION_STATUS_TEXT = {
    "can_appeal": "Có thể kháng cáo",  # getPenaltyDetails appeal_status 0
    "under_review": "Đang xét kháng cáo",  # appeal_status 1
    "penalized": "Đã xử phạt",  # any other appeal_status
    "appealed": "Đã nộp kháng cáo",  # set by the app after submitting an appeal
    "pending": "Chờ giải trình",
}


def violation_status_text(status: object) -> str:
    key = str(status or "pending")
    return _VIOLATION_STATUS_TEXT.get(key, key)


def format_appeal_deadline(value: object) -> str:
    """Appeal deadline as dd/mm/YYYY. TikTok sends epoch seconds (sometimes milliseconds) as a string; appeal
    actions store "YYYY-MM-DD[ HH:MM:SS]". Anything else is shown as-is, empty as an em dash."""
    text = str(value).strip() if value is not None else ""
    if not text:
        return "—"
    if text.isdigit():
        stamp = int(text)
        if stamp > 10**11:  # milliseconds
            stamp //= 1000
        try:
            return datetime.fromtimestamp(stamp).strftime("%d/%m/%Y")
        except (OverflowError, OSError, ValueError):
            return text
    try:
        return datetime.fromisoformat(text).strftime("%d/%m/%Y")
    except ValueError:
        return text


# Legacy hex colors (picked for a dark background) -> semantic Fluent status colors that read well
# on the app's light theme and follow dark mode.
_HEX_TO_KIND = {
    "#10B981": "success",
    "#059669": "success",
    "#34D399": "success",
    "#F59E0B": "warning",
    "#EA580C": "warning",
    "#EF4444": "danger",
    "#DC2626": "danger",
    "#F87171": "danger",
    "#38BDF8": "info",
    "#0284C7": "info",
    "#64748B": "neutral",
    "#94A3B8": "neutral",
    "#F1F5F9": "neutral",
}


def _semantic(color: str) -> str:
    kind = _HEX_TO_KIND.get(color.upper(), color) if color.startswith("#") else color
    return status_color(kind) if kind in ("success", "warning", "danger", "info", "neutral") else color


class HealthKpiCard(QFrame):
    """Modern KPI metric card with title, large value, and color badge."""

    def __init__(self, title: str, initial_value: str = "—", color: str = "#64748B", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        style_card(self, object_name="kpiCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(f"color: {status_color('neutral')}; font-size: 11px; font-weight: 600;")
        layout.addWidget(self.title_label)

        self.value_label = QLabel(initial_value)
        self.value_label.setStyleSheet(f"color: {_semantic(color)}; font-size: 15px; font-weight: 600;")
        layout.addWidget(self.value_label)

    def set_value(self, value_text: str, color: str = "neutral") -> None:
        self.value_label.setText(value_text)
        self.value_label.setStyleSheet(f"color: {_semantic(color)}; font-size: 15px; font-weight: 600;")


class AccountHealthDialog(QDialog):
    """Dialog inspecting TikTok account health standing, community strikes, originality violations, and appeals."""

    def __init__(
        self,
        profile_id: int,
        parent: QWidget | None = None,
        db_path: Path | str | None = None,
    ) -> None:
        super().__init__(parent)
        self.profile_id = profile_id
        self.db_path = Path(db_path or "data/app.db")
        self.moderation_service = TikTokModerationService(db_path=self.db_path)
        self._closed = False

        self.setWindowTitle(f"Kiểm Tra Chất Lượng & Gậy Vi Phạm TikTok — Profile #{profile_id}")
        self.setMinimumSize(850, 560)
        self.resize(1020, 720)

        self._build_ui()
        self._load_data()

    def exec(self) -> int:
        """Explicit Python wrapper over QDialog.exec for testability and lifecycle hooks."""
        return super().exec()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*STANDARD_DIALOG_MARGINS)
        layout.setSpacing(STANDARD_DIALOG_SPACING)

        # 1. Header Title & Top Actions
        header = create_dialog_header(
            icon=FluentIcon.HEART,
            title=f"Kiểm Tra Chất Lượng & Gậy Vi Phạm TikTok — Profile #{self.profile_id}",
            subtitle="Giám sát cảnh báo vi phạm bản quyền, gậy cộng đồng, điểm phạt và tiến độ kháng cáo tài khoản.",
            parent=self,
        )
        layout.addWidget(header)

        top_actions_row = QHBoxLayout()
        top_actions_row.addStretch(1)

        self.btn_check_appeals = PushButton(FluentIcon.SYNC, "Kiểm Tra Tiến Độ Kháng Cáo", self)
        self.btn_check_appeals.clicked.connect(self._on_check_appeals_async)
        top_actions_row.addWidget(self.btn_check_appeals)

        self.btn_refresh = PrimaryPushButton(FluentIcon.SPEED_HIGH, "Quét Toàn Kênh", self)
        self.btn_refresh.clicked.connect(self._run_scan_async)
        top_actions_row.addWidget(self.btn_refresh)
        layout.addLayout(top_actions_row)

        # 2. 5 KPI Status Cards (including Creator Rewards countdown)
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(10)

        self.card_standing = HealthKpiCard("CHẤT LƯỢNG TÀI KHOẢN", "Chưa xác minh", "#64748B")
        self.card_strikes = HealthKpiCard("GẬY TÍCH LŨY", "—", "#64748B")
        self.card_penalty = HealthKpiCard("ĐIỂM PHẠT", "0 đ", "#64748B")
        self.card_shadowban = HealthKpiCard("ƯỚC TÍNH RỦI RO", "Bình thường", "#10B981")
        self.card_reapply_countdown = HealthKpiCard("QUỸ SÁNG TẠO (REWARDS)", "Đủ điều kiện", "#10B981")

        cards_layout.addWidget(self.card_standing)
        cards_layout.addWidget(self.card_strikes)
        cards_layout.addWidget(self.card_penalty)
        cards_layout.addWidget(self.card_shadowban)
        cards_layout.addWidget(self.card_reapply_countdown)
        layout.addLayout(cards_layout)

        # 3. Creator Rewards Program Re-application Banner
        self.reapply_banner = QFrame()
        style_card(self.reapply_banner, object_name="reapplyBanner")
        rb_layout = QHBoxLayout(self.reapply_banner)
        rb_layout.setContentsMargins(14, 8, 14, 8)

        self.lbl_reapply_status = QLabel("Trạng thái Quỹ Nhà Sáng Tạo:")
        self.lbl_reapply_status.setStyleSheet("font-size: 13px; font-weight: 500;")
        rb_layout.addWidget(self.lbl_reapply_status)
        rb_layout.addStretch(1)

        self.btn_reapply_creator = PrimaryPushButton(FluentIcon.SEND, "Nộp Lại Đơn Gia Nhập Quỹ Sáng Tạo", self)
        self.btn_reapply_creator.clicked.connect(self._on_reapply_creator_rewards_async)
        rb_layout.addWidget(self.btn_reapply_creator)
        layout.addWidget(self.reapply_banner)

        # 4. Diagnostic Banner
        self.diag_frame = QFrame()
        style_card(self.diag_frame, object_name="diagCard")
        diag_layout = QVBoxLayout(self.diag_frame)
        diag_layout.setContentsMargins(12, 8, 12, 8)
        diag_layout.setSpacing(4)

        self.lbl_diag_title = QLabel("Chẩn đoán thuật toán & Cảnh báo phân phối:")
        self.lbl_diag_title.setStyleSheet(f"font-weight: 600; color: {status_color('neutral')}; font-size: 12px;")
        self.lbl_diag_content = QLabel("Đang nạp dữ liệu phân tích...")
        self.lbl_diag_content.setStyleSheet("font-size: 13px;")
        self.lbl_diag_content.setWordWrap(True)

        diag_layout.addWidget(self.lbl_diag_title)
        diag_layout.addWidget(self.lbl_diag_content)
        layout.addWidget(self.diag_frame)

        # 5. Tabs: Video Vi Phạm & Quản lý
        self.tabs = style_tab_widget(QTabWidget())
        layout.addWidget(self.tabs, 1)

        # Tab 1: Video Vi phạm & Gậy nguyên tác
        tab_violate = QWidget()
        v_layout = QVBoxLayout(tab_violate)
        v_layout.setContentsMargins(6, 10, 6, 6)
        v_layout.setSpacing(8)

        self.table_violate = style_plain_table(QTableWidget(0, 5))
        self.table_violate.setHorizontalHeaderLabels(VIOLATION_COLUMNS)
        header_date = self.table_violate.horizontalHeaderItem(3)
        if header_date is not None:
            header_date.setToolTip("Ngày TikTok xử phạt video. TikTok không gửi hạn chót kháng cáo.")
        h_header(self.table_violate).setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h_header(self.table_violate).setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h_header(self.table_violate).setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h_header(self.table_violate).setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table_violate.setAlternatingRowColors(True)
        v_header(self.table_violate).setVisible(False)
        self.table_violate.itemSelectionChanged.connect(self._on_violate_selection_changed)
        v_layout.addWidget(self.table_violate, 1)

        # Action bar under violate table
        action_bar_v = QHBoxLayout()
        action_bar_v.addStretch(1)

        self.btn_appeal_video = PrimaryPushButton(FluentIcon.CERTIFICATE, "Nộp Đơn Kháng Cáo Video Đang Chọn...", self)
        self.btn_appeal_video.setEnabled(False)
        self.btn_appeal_video.clicked.connect(lambda: self._on_appeal_selected_video())
        action_bar_v.addWidget(self.btn_appeal_video)
        v_layout.addLayout(action_bar_v)

        self.tabs.addTab(tab_violate, "Video Bị Gậy Vi Phạm && Gậy Nguyên Tác")

        # Tab 2: Lịch Sử Vé Kháng Cáo
        tab_appeals = QWidget()
        a_layout = QVBoxLayout(tab_appeals)
        a_layout.setContentsMargins(6, 10, 6, 6)

        self.table_appeals = style_plain_table(QTableWidget(0, 5))
        self.table_appeals.setHorizontalHeaderLabels(
            ["Mã Vé", "Loại kháng cáo", "Đối tượng", "Lý do nộp", "Trạng thái xét duyệt"]
        )
        h_header(self.table_appeals).setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table_appeals.setAlternatingRowColors(True)
        v_header(self.table_appeals).setVisible(False)
        a_layout.addWidget(self.table_appeals, 1)

        self.tabs.addTab(tab_appeals, "Lịch Sử Vé Kháng Cáo (Appeals)")

        # Tab 3: Từ Khóa Tìm Kiếm SEO && Phân Bổ Nguồn View (Deep Telemetry)
        tab_deep = QWidget()
        d_layout = QVBoxLayout(tab_deep)
        d_layout.setContentsMargins(6, 10, 6, 6)
        d_layout.setSpacing(8)

        self.table_deep_analytics = style_plain_table(QTableWidget(0, 6))
        self.table_deep_analytics.setHorizontalHeaderLabels(
            ["Video ID", "Tiêu đề video", "Lượt xem", "Xem hết", "Nguồn View (FYF/Search)", "Top Từ Khóa Tìm Kiếm (SEO FYP)"]
        )
        h_header(self.table_deep_analytics).setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h_header(self.table_deep_analytics).setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        h_header(self.table_deep_analytics).setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table_deep_analytics.setAlternatingRowColors(True)
        v_header(self.table_deep_analytics).setVisible(False)
        d_layout.addWidget(self.table_deep_analytics, 1)

        self.tabs.addTab(tab_deep, "Từ Khóa SEO (FYP) && Nguồn View")

    def _on_violate_selection_changed(self) -> None:
        """Enables or disables the appeal button based on row selection."""
        selection = self.table_violate.selectionModel()
        selected_rows = selection.selectedRows() if selection is not None else []
        if not selected_rows:
            self.btn_appeal_video.setEnabled(False)
            return

        row = selected_rows[0].row()
        st_item = self.table_violate.item(row, 4)
        status = st_item.text() if st_item else ""
        # If already appealed, disable button
        self.btn_appeal_video.setEnabled(status != "Đã nộp kháng cáo")

    def _alive(self) -> bool:
        """False once the dialog is closed or its C++ object destroyed (late results are dropped)."""
        return not self._closed and not sip.isdeleted(self)

    def _guard(self, fn: Callable[..., None]) -> Callable[..., None]:
        """Wraps a GUI callback so a background result arriving after close is ignored."""

        def guarded(*args: Any) -> None:
            if self._alive():
                fn(*args)

        return guarded

    def done(self, result: int) -> None:
        self._closed = True
        super().done(result)

    def closeEvent(self, event: QCloseEvent | None) -> None:
        self._closed = True
        super().closeEvent(event)

    def _run(
        self,
        fn: Callable[..., Any],
        *args: Any,
        on_result: Callable[[Any], None],
        on_error: Callable[[str], None],
    ) -> None:
        """Runs ``fn`` on the UI thread pool; callbacks come back on the GUI thread, if still open."""
        run_task(fn, *args, on_result=self._guard(on_result), on_error=self._guard(on_error))

    def _load_data(self) -> None:
        """Loads profile health, creator rewards countdown and violations off the GUI thread."""
        self._run(
            fetch_health_data,
            self.db_path,
            self.profile_id,
            on_result=self._apply_health_data,
            on_error=lambda err: logger.warning("Account health load failed: %s", err),
        )

    def _apply_health_data(self, data: dict[str, Any] | None) -> None:
        """Renders data from fetch_health_data (GUI thread)."""
        if not data:
            return
        p = data["profile"]
        violations = data["violations"]
        appeals = data["appeals"]

        standing = str(p["account_standing"] or "Chưa xác minh").strip()
        strikes = int(p["strike_count"] or 0)
        points = int(p["total_penalty_points"] or 0)
        sdb = str(p["sdb"] or "0").strip()
        date_reapply = p["date_reapply"]

        # 1. Update KPI Cards
        if standing == "Good":
            self.card_standing.set_value("Good", "#10B981")
        elif standing == "Warning":
            self.card_standing.set_value("Warning", "#F59E0B")
        elif standing in ("High Risk", "high_risk"):
            self.card_standing.set_value("High Risk", "#EF4444")
        elif standing in ("Suspended", "banned"):
            self.card_standing.set_value("Đình chỉ", "#DC2626")
        else:
            self.card_standing.set_value(standing, "#38BDF8")

        if strikes == 0:
            self.card_strikes.set_value("0 / 3 Gậy", "#10B981")
        elif strikes == 1:
            self.card_strikes.set_value("1 / 3 Gậy", "#F59E0B")
        elif strikes == 2:
            self.card_strikes.set_value("2 / 3 Gậy", "#EA580C")
        else:
            self.card_strikes.set_value(f"{strikes} / 3 Gậy", "#EF4444")

        self.card_penalty.set_value(f"{points} đ", "#0284C7" if points == 0 else "#EF4444")

        if sdb == "1":
            self.card_shadowban.set_value("Dấu hiệu Shadowban", "#EF4444")
        else:
            self.card_shadowban.set_value("Bình thường (FYF OK)", "#10B981")

        # 2. Update Creator Rewards Countdown & Button
        if date_reapply:
            try:
                target_dt = datetime.fromisoformat(str(date_reapply))
                now_dt = datetime.now()
                if target_dt.tzinfo is not None and now_dt.tzinfo is None:
                    now_dt = now_dt.astimezone()
                elif target_dt.tzinfo is None and now_dt.tzinfo is not None:
                    target_dt = target_dt.astimezone()

                seconds = (target_dt - now_dt).total_seconds()
                if seconds > 0:
                    days_left = max(1, math.ceil(seconds / 86400))
                    self.card_reapply_countdown.set_value(f"Còn {days_left} ngày", "#F59E0B")
                    self.lbl_reapply_status.setText(
                        f"Đang chịu thời gian phạt Quỹ Sáng Tạo: Mở lại ngày {str(date_reapply)[:10]} (còn {days_left} ngày)."
                    )
                    self.btn_reapply_creator.setEnabled(False)
                    self.btn_reapply_creator.setText(f"Còn {days_left} ngày để nộp lại")
                else:
                    self._set_reapply_eligible()
            except Exception:
                self._set_reapply_eligible()
        else:
            self._set_reapply_eligible()

        # 3. Update Diagnostic Content
        if strikes > 0:
            self.lbl_diag_content.setText(
                f"Cảnh báo: Kênh đang bị dính {strikes}/3 gậy vi phạm chính sách hoặc gậy nguyên tác. "
                "Vui lòng nộp đơn kháng cáo cho các video trước hạn chót để tránh bị đình chỉ kênh vĩnh viễn."
            )
            self.lbl_diag_content.setStyleSheet(f"color: {status_color('danger')}; font-size: 13px;")
        else:
            self.lbl_diag_content.setText(
                "Kênh ở trạng thái khỏe mạnh: Không có gậy tích lũy. Video phân phối bình thường trên For You Page (FYP)."
            )
            self.lbl_diag_content.setStyleSheet(f"color: {status_color('success')}; font-size: 13px;")
        # 4. Violated videos
        self.table_violate.setRowCount(len(violations))
        for row_idx, v in enumerate(violations):
            v_dict = v
            self.table_violate.setItem(row_idx, 0, QTableWidgetItem(str(v_dict.get("video_id") or "")))
            self.table_violate.setItem(
                row_idx, 1, QTableWidgetItem(str(v_dict.get("title") or "Video không tiêu đề"))
            )

            v_title = str(v_dict.get("violate_title") or "Vi phạm Chính sách")
            v_item = QTableWidgetItem(v_title)
            if "nguyên tác" in v_title.lower() or "unoriginal" in v_title.lower():
                v_item.setForeground(QColor(status_color("warning")))
            else:
                v_item.setForeground(QColor(status_color("danger")))
            self.table_violate.setItem(row_idx, 2, v_item)

            deadline = format_appeal_deadline(v_dict.get("appeal_date"))
            self.table_violate.setItem(row_idx, 3, QTableWidgetItem(deadline))

            self.table_violate.setItem(row_idx, 4, QTableWidgetItem(violation_status_text(v_dict.get("status"))))

        # 5. Account appeals
        self.table_appeals.setRowCount(len(appeals))
        for row_idx, a in enumerate(appeals):
            a_dict = a
            self.table_appeals.setItem(row_idx, 0, QTableWidgetItem(f"#{a_dict.get('id')}"))
            self.table_appeals.setItem(row_idx, 1, QTableWidgetItem(str(a_dict.get("appeal_type") or "Kháng gậy")))
            self.table_appeals.setItem(row_idx, 2, QTableWidgetItem(str(a_dict.get("object_id") or "")))
            self.table_appeals.setItem(row_idx, 3, QTableWidgetItem(str(a_dict.get("reason") or "")))
            self.table_appeals.setItem(row_idx, 4, QTableWidgetItem(str(a_dict.get("status") or "Đang xử lý")))

        # 6. Deep Telemetry & Search Terms (SEO FYP)
        deep_list = data.get("deep_analytics") or []
        self.table_deep_analytics.setRowCount(len(deep_list))
        import json as _json
        for row_idx, d in enumerate(deep_list):
            v_id = str(d.get("video_id") or "")
            title = str(d.get("title") or "Video không tiêu đề")
            views = int(d.get("views") or 0)
            fn_rate = float(d.get("finish_rate") or 0.0)

            # Parse traffic sources
            ts_raw = d.get("traffic_sources_json")
            ts_str = "—"
            if ts_raw:
                try:
                    ts = _json.loads(ts_raw) if isinstance(ts_raw, str) else ts_raw
                    fyf = ts.get("for_you")
                    search = ts.get("search")
                    if fyf is not None or search is not None:
                        ts_str = f"FYF: {fyf or 0:.1f}% | Search: {search or 0:.1f}%"
                except Exception:
                    pass

            # Parse search terms
            st_raw = d.get("search_terms_json")
            terms_str = "—"
            if st_raw:
                try:
                    terms = _json.loads(st_raw) if isinstance(st_raw, str) else st_raw
                    if isinstance(terms, list) and terms:
                        terms_str = ", ".join(f"{t.get('keyword')} ({t.get('percentage')}%)" for t in terms[:3])
                except Exception:
                    pass

            self.table_deep_analytics.setItem(row_idx, 0, QTableWidgetItem(v_id))
            self.table_deep_analytics.setItem(row_idx, 1, QTableWidgetItem(title))
            self.table_deep_analytics.setItem(row_idx, 2, QTableWidgetItem(f"{views:,}"))
            fn_item = QTableWidgetItem(f"{fn_rate:.1f}%" if fn_rate > 0 else "—")
            if fn_rate >= 15.0:
                fn_item.setForeground(QColor(status_color("success")))
            self.table_deep_analytics.setItem(row_idx, 3, fn_item)
            self.table_deep_analytics.setItem(row_idx, 4, QTableWidgetItem(ts_str))
            self.table_deep_analytics.setItem(row_idx, 5, QTableWidgetItem(terms_str))

    def _set_reapply_eligible(self) -> None:
        """Sets UI state to allow re-applying to Creator Rewards."""
        self.card_reapply_countdown.set_value("Sẵn sàng nộp lại", "#10B981")
        self.lbl_reapply_status.setText("Kênh đủ điều kiện nộp lại đơn tham gia Quỹ Nhà Sáng Tạo (Creator Rewards).")
        self.btn_reapply_creator.setEnabled(True)
        self.btn_reapply_creator.setText("Nộp Lại Đơn Gia Nhập Quỹ Sáng Tạo")

    def _on_appeal_selected_video(self, mock_reason: str | None = None) -> None:
        """Submits an appeal for the currently selected video."""
        selection = self.table_violate.selectionModel()
        selected_rows = selection.selectedRows() if selection is not None else []
        if not selected_rows:
            return

        row = selected_rows[0].row()
        id_item = self.table_violate.item(row, 0)
        if id_item is None:
            return
        video_id = id_item.text()

        reason = mock_reason
        if not reason:
            reasons = [
                "1. Video do chính chủ sáng tạo nguyên tác, tuân thủ tiêu chuẩn cộng đồng TikTok.",
                "2. Đã có bản quyền hợp pháp đối với toàn bộ âm thanh và hình ảnh sử dụng.",
                "3. Nội dung bình luận, đánh giá hoặc giáo dục có tính biến đổi sáng tạo (Fair Use).",
            ]
            item, ok = QInputDialog.getItem(
                self,
                "Nộp Đơn Kháng Cáo Video",
                f"Chọn lý do kháng nghị cho Video #{video_id}:",
                reasons,
                0,
                False,
            )
            if not ok or not item:
                return
            reason = item

        # Optimistic UI update
        self.table_violate.setItem(row, 4, QTableWidgetItem("Đã nộp kháng cáo"))
        self.btn_appeal_video.setEnabled(False)

        def on_result(res: dict[str, Any]) -> None:
            self._load_data()
            if res.get("ok"):
                InfoBar.success(
                    title="Đã Nộp Kháng Cáo",
                    content=res.get("message") or f"Đơn kháng nghị cho video #{video_id} đã được gửi thành công.",
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
            else:
                InfoBar.error(
                    title="Lỗi Nộp Kháng Cáo",
                    content=res.get("error") or "Không thể nộp đơn kháng cáo.",
                    position=InfoBarPosition.TOP,
                    parent=self,
                )

        def on_error(err: str) -> None:
            InfoBar.error(title="Lỗi Nộp Kháng Cáo", content=err, position=InfoBarPosition.TOP, parent=self)

        self._run(
            self.moderation_service.submit_video_appeal,
            self.profile_id,
            video_id,
            reason,
            on_result=on_result,
            on_error=on_error,
        )

    def _on_check_appeals_async(self) -> None:
        """Checks appeal status and reconciles channel health asynchronously."""
        self.btn_check_appeals.setEnabled(False)
        self.btn_check_appeals.setText("Đang kiểm tra...")

        def restore_button() -> None:
            self.btn_check_appeals.setEnabled(True)
            self.btn_check_appeals.setText("Kiểm Tra Tiến Độ Kháng Cáo")

        def on_result(res: dict[str, Any]) -> None:
            restore_button()
            self._load_data()
            resolved = res.get("resolved_count", 0)
            rejected = res.get("rejected_count", 0)
            reviewing = res.get("reviewing_count", 0)
            detail_str = f"Đã cập nhật {res.get('appeals_count', 0)} vé kháng cáo."
            if resolved or rejected or reviewing:
                detail_str += f" (Đã gỡ gậy: {resolved}, Bác bỏ: {rejected}, Đang thẩm định: {reviewing})"
            InfoBar.success(
                title="Đồng Bộ Vé Kháng Cáo Hoàn Tất",
                content=detail_str,
                position=InfoBarPosition.TOP,
                parent=self,
            )

        def on_error(err: str) -> None:
            restore_button()
            InfoBar.error(title="Lỗi Kiểm Tra Kháng Cáo", content=err, position=InfoBarPosition.TOP, parent=self)

        self._run(self.moderation_service.check_appeal_status, self.profile_id, on_result=on_result, on_error=on_error)

    def _on_reapply_creator_rewards_async(self) -> None:
        """Submits re-application to Creator Rewards Program asynchronously."""
        self.btn_reapply_creator.setEnabled(False)
        self.btn_reapply_creator.setText("Đang gửi đơn...")

        def on_result(res: dict[str, Any]) -> None:
            self._load_data()
            if res.get("ok"):
                InfoBar.success(
                    title="Gia Nhập Quỹ Sáng Tạo Thành Công",
                    content="Đã nộp lại đơn tham gia Quỹ Nhà Sáng Tạo thành công. Trạng thái kênh đã phục hồi.",
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
            else:
                InfoBar.warning(
                    title="Chưa Thể Nộp Đơn",
                    content=res.get("error", "Vui lòng chờ hết thời gian phạt."),
                    position=InfoBarPosition.TOP,
                    parent=self,
                )

        def on_error(err: str) -> None:
            self._load_data()
            InfoBar.error(title="Lỗi Nộp Đơn Quỹ Sáng Tạo", content=err, position=InfoBarPosition.TOP, parent=self)

        self._run(
            self.moderation_service.submit_creator_rewards_reapply,
            self.profile_id,
            on_result=on_result,
            on_error=on_error,
        )

    def _run_scan_async(self) -> None:
        """Executes full moderation scan in background thread."""
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("Đang quét...")

        def restore_button() -> None:
            self.btn_refresh.setEnabled(True)
            self.btn_refresh.setText("Quét Toàn Kênh")

        def on_result(res: dict[str, Any]) -> None:
            restore_button()
            self._load_data()
            label = res.get("standing", {}).get("status_label", "OK")
            InfoBar.success(
                title="Quét Sức Khỏe Kênh Hoàn Tất",
                content=f"Đã cập nhật tình trạng: {label} ({res.get('violations_count', 0)} video gậy).",
                position=InfoBarPosition.TOP,
                parent=self,
            )

        def on_error(err: str) -> None:
            restore_button()
            InfoBar.error(title="Lỗi Quét Sức Khỏe", content=err, position=InfoBarPosition.TOP, parent=self)

        self._run(self.moderation_service.scan_full_channel_health, self.profile_id, on_result=on_result, on_error=on_error)

__all__ = ["AccountHealthDialog", "HealthKpiCard"]
