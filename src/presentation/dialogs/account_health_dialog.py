"""
AccountHealthDialog — Giao diện Kiểm tra Chất lượng Tài khoản, Gậy Vi phạm & Gậy Nguyên tác TikTok.
Bổ sung:
- Kháng cáo Video Vi phạm / Gậy Nguyên tác (Video Appeal)
- Kiểm tra Tiến độ Kháng cáo (Check Appeals)
- Đếm ngược & Nộp lại Đơn Quỹ Nhà Sáng Tạo (Creator Rewards Re-application)
- Tích hợp GoLogin SDK & Proxy Routing
"""

from __future__ import annotations

import math
import sqlite3
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor
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

from src.infrastructure.tiktok.moderation_service import TikTokModerationService
from src.presentation.dialogs.dialog_helpers import (
    STANDARD_DIALOG_MARGINS,
    STANDARD_DIALOG_SPACING,
    create_dialog_header,
)


class HealthKpiCard(QFrame):
    """Modern KPI metric card with title, large value, and color badge."""

    def __init__(self, title: str, initial_value: str = "—", color: str = "#64748B", parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 8px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 600; text-transform: uppercase;")
        layout.addWidget(self.title_label)

        self.value_label = QLabel(initial_value)
        self.value_label.setStyleSheet(f"color: {color}; font-size: 15px; font-weight: bold;")
        layout.addWidget(self.value_label)

    def set_value(self, value_text: str, color: str = "#F1F5F9") -> None:
        self.value_label.setText(value_text)
        self.value_label.setStyleSheet(f"color: {color}; font-size: 15px; font-weight: bold;")


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

        self.setWindowTitle(f"🛡️ Kiểm Tra Chất Lượng & Gậy Vi Phạm TikTok — Profile #{profile_id}")
        self.setStyleSheet("""
            QDialog {
                background-color: #0B0F17;
                color: #F1F5F9;
            }
            QTabWidget::pane {
                background-color: #0F172A;
                border: 1px solid #1E293B;
                border-radius: 8px;
            }
            QTabBar::tab {
                background-color: #0B0F17;
                color: #94A3B8;
                padding: 8px 18px;
                font-weight: 600;
                font-size: 12px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background-color: #0F172A;
                color: #38BDF8;
                border-bottom: 2px solid #38BDF8;
            }
            QTableWidget {
                background-color: #0F172A;
                alternate-background-color: #131E30;
                color: #F1F5F9;
                gridline-color: #1E293B;
                border: 1px solid #1E293B;
                border-radius: 6px;
                selection-background-color: rgba(56, 189, 248, 0.2);
                selection-color: #FFFFFF;
            }
            QHeaderView::section {
                background-color: #1E293B;
                color: #94A3B8;
                font-weight: 600;
                font-size: 12px;
                border: none;
                border-right: 1px solid #334155;
                border-bottom: 1px solid #334155;
                padding: 6px 8px;
            }
        """)
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
        self.reapply_banner.setStyleSheet("background-color: #0F172A; border: 1px solid #1E293B; border-radius: 8px;")
        rb_layout = QHBoxLayout(self.reapply_banner)
        rb_layout.setContentsMargins(14, 8, 14, 8)

        self.lbl_reapply_status = QLabel("💎 Trạng thái Quỹ Nhà Sáng Tạo:")
        self.lbl_reapply_status.setStyleSheet("color: #E2E8F0; font-size: 13px; font-weight: 500;")
        rb_layout.addWidget(self.lbl_reapply_status)
        rb_layout.addStretch(1)

        self.btn_reapply_creator = PrimaryPushButton(FluentIcon.SEND, "Nộp Lại Đơn Gia Nhập Quỹ Sáng Tạo", self)
        self.btn_reapply_creator.clicked.connect(self._on_reapply_creator_rewards_async)
        rb_layout.addWidget(self.btn_reapply_creator)
        layout.addWidget(self.reapply_banner)

        # 4. Diagnostic Banner
        self.diag_frame = QFrame()
        self.diag_frame.setStyleSheet("background-color: #1E293B; border-radius: 8px; border: 1px solid #334155;")
        diag_layout = QVBoxLayout(self.diag_frame)
        diag_layout.setContentsMargins(12, 8, 12, 8)
        diag_layout.setSpacing(4)

        self.lbl_diag_title = QLabel("📋 Chẩn đoán thuật toán & Cảnh báo phân phối:")
        self.lbl_diag_title.setStyleSheet("font-weight: bold; color: #94A3B8; font-size: 12px;")
        self.lbl_diag_content = QLabel("Đang nạp dữ liệu phân tích...")
        self.lbl_diag_content.setStyleSheet("color: #E2E8F0; font-size: 13px;")
        self.lbl_diag_content.setWordWrap(True)

        diag_layout.addWidget(self.lbl_diag_title)
        diag_layout.addWidget(self.lbl_diag_content)
        layout.addWidget(self.diag_frame)

        # 5. Tabs: Video Vi Phạm & Quản lý
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        # Tab 1: Video Vi phạm & Gậy nguyên tác
        tab_violate = QWidget()
        v_layout = QVBoxLayout(tab_violate)
        v_layout.setContentsMargins(6, 10, 6, 6)
        v_layout.setSpacing(8)

        self.table_violate = QTableWidget(0, 5)
        self.table_violate.setHorizontalHeaderLabels(
            ["Video ID", "Tiêu đề video", "Loại gậy vi phạm", "Hạn nộp đơn kháng cáo", "Trạng thái"]
        )
        self.table_violate.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_violate.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_violate.setAlternatingRowColors(True)
        self.table_violate.verticalHeader().setVisible(False)
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
        v_layout.addLayout(action_bar_v)

        self.tabs.addTab(tab_violate, "⚠️ Video Bị Gậy Vi Phạm & Gậy Nguyên Tác")

        # Tab 2: Lịch Sử Vé Kháng Cáo
        tab_appeals = QWidget()
        a_layout = QVBoxLayout(tab_appeals)
        a_layout.setContentsMargins(6, 10, 6, 6)

        self.table_appeals = QTableWidget(0, 5)
        self.table_appeals.setHorizontalHeaderLabels(
            ["Mã Vé", "Loại kháng cáo", "Đối tượng", "Lý do nộp", "Trạng thái xét duyệt"]
        )
        self.table_appeals.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table_appeals.setAlternatingRowColors(True)
        self.table_appeals.verticalHeader().setVisible(False)
        a_layout.addWidget(self.table_appeals, 1)

        self.tabs.addTab(tab_appeals, "📝 Lịch Sử Vé Kháng Cáo (Appeals)")

    def _on_violate_selection_changed(self) -> None:
        """Enables or disables the appeal button based on row selection."""
        selected_rows = self.table_violate.selectionModel().selectedRows()
        if not selected_rows:
            self.btn_appeal_video.setEnabled(False)
            return

        row = selected_rows[0].row()
        st_item = self.table_violate.item(row, 4)
        status = st_item.text() if st_item else ""
        # If already appealed, disable button
        self.btn_appeal_video.setEnabled(status != "Đã nộp kháng cáo")

    def _load_data(self) -> None:
        """Loads profile health, creator rewards countdown, and video violations from database."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            p = conn.execute("SELECT * FROM profiles WHERE id=?", (self.profile_id,)).fetchone()
            if not p:
                return

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
                        self.card_reapply_countdown.set_value(f"⏳ Còn {days_left} ngày", "#F59E0B")
                        self.lbl_reapply_status.setText(
                            f"⏳ Đang chịu thời gian phạt Quỹ Sáng Tạo: Mở lại ngày {str(date_reapply)[:10]} (còn {days_left} ngày)."
                        )
                        self.btn_reapply_creator.setEnabled(False)
                        self.btn_reapply_creator.setText(f"⏳ Còn {days_left} ngày để nộp lại")
                        self.btn_reapply_creator.setStyleSheet(
                            "background-color: #334155; color: #94A3B8; padding: 6px 16px; border-radius: 6px; font-weight: bold;"
                        )
                    else:
                        self._set_reapply_eligible()
                except Exception:
                    self._set_reapply_eligible()
            else:
                self._set_reapply_eligible()

            # 3. Update Diagnostic Content
            if strikes > 0:
                self.lbl_diag_content.setText(
                    f"⚠️ Cảnh báo: Kênh đang bị dính {strikes}/3 gậy vi phạm chính sách hoặc gậy nguyên tác. "
                    "Vui lòng nộp đơn kháng cáo cho các video trước hạn chót để tránh bị đình chỉ kênh vĩnh viễn."
                )
                self.lbl_diag_content.setStyleSheet("color: #F87171; font-size: 13px;")
            else:
                self.lbl_diag_content.setText(
                    "✅ Kênh ở trạng thái khỏe mạnh: Không có gậy tích lũy. Video phân phối bình thường trên For You Page (FYP)."
                )
                self.lbl_diag_content.setStyleSheet("color: #34D399; font-size: 13px;")

            # 4. Load violateVideos
            violations = conn.execute(
                "SELECT * FROM violateVideos WHERE profile_id=? ORDER BY id DESC",
                (self.profile_id,),
            ).fetchall()
            self.table_violate.setRowCount(len(violations))
            for row_idx, v in enumerate(violations):
                v_dict = dict(v)
                self.table_violate.setItem(row_idx, 0, QTableWidgetItem(str(v_dict.get("video_id") or "")))
                self.table_violate.setItem(
                    row_idx, 1, QTableWidgetItem(str(v_dict.get("title") or "Video không tiêu đề"))
                )

                v_title = str(v_dict.get("violate_title") or "Vi phạm Chính sách")
                v_item = QTableWidgetItem(v_title)
                if "nguyên tác" in v_title.lower() or "unoriginal" in v_title.lower():
                    v_item.setForeground(QColor("#F59E0B"))
                else:
                    v_item.setForeground(QColor("#EF4444"))
                self.table_violate.setItem(row_idx, 2, v_item)

                self.table_violate.setItem(row_idx, 3, QTableWidgetItem(str(v_dict.get("appeal_date") or "—")))

                st_text = str(v_dict.get("status") or "pending")
                if st_text == "appealed":
                    disp_status = "Đã nộp kháng cáo"
                elif st_text == "pending":
                    disp_status = "Chờ giải trình"
                else:
                    disp_status = st_text
                self.table_violate.setItem(row_idx, 4, QTableWidgetItem(disp_status))

            # 5. Load accountAppeals
            appeals = conn.execute(
                "SELECT * FROM accountAppeals WHERE profile_id=? ORDER BY id DESC",
                (self.profile_id,),
            ).fetchall()
            self.table_appeals.setRowCount(len(appeals))
            for row_idx, a in enumerate(appeals):
                a_dict = dict(a)
                self.table_appeals.setItem(row_idx, 0, QTableWidgetItem(f"#{a_dict.get('id')}"))
                self.table_appeals.setItem(row_idx, 1, QTableWidgetItem(str(a_dict.get("appeal_type") or "Kháng gậy")))
                self.table_appeals.setItem(row_idx, 2, QTableWidgetItem(str(a_dict.get("object_id") or "")))
                self.table_appeals.setItem(row_idx, 3, QTableWidgetItem(str(a_dict.get("reason") or "")))
                self.table_appeals.setItem(row_idx, 4, QTableWidgetItem(str(a_dict.get("status") or "Đang xử lý")))

        finally:
            conn.close()

    def _set_reapply_eligible(self) -> None:
        """Sets UI state to allow re-applying to Creator Rewards."""
        self.card_reapply_countdown.set_value("Sẵn sàng nộp lại", "#10B981")
        self.lbl_reapply_status.setText("🟢 Kênh đủ điều kiện nộp lại đơn tham gia Quỹ Nhà Sáng Tạo (Creator Rewards).")
        self.btn_reapply_creator.setEnabled(True)
        self.btn_reapply_creator.setText("💎 Nộp Lại Đơn Gia Nhập Quỹ Sáng Tạo")
        self.btn_reapply_creator.setStyleSheet(
            "background-color: #059669; color: white; padding: 6px 16px; border-radius: 6px; font-weight: bold;"
        )

    def _on_appeal_selected_video(self, mock_reason: str | None = None) -> None:
        """Submits an appeal for the currently selected video."""
        selected_rows = self.table_violate.selectionModel().selectedRows()
        if not selected_rows:
            return

        row = selected_rows[0].row()
        video_id = self.table_violate.item(row, 0).text()

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

        import concurrent.futures

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(
            self.moderation_service.submit_video_appeal,
            self.profile_id,
            video_id,
            reason,
        )

        def check_appeal():
            if future.done():
                timer.stop()
                try:
                    future.result()
                    self._load_data()
                    InfoBar.success(
                        title="Đã Nộp Kháng Cáo",
                        content=f"Đơn kháng nghị cho video #{video_id} đã được gửi thành công.",
                        position=InfoBarPosition.TOP,
                        parent=self,
                    )
                except Exception as e:
                    InfoBar.error(
                        title="Lỗi Nộp Kháng Cáo",
                        content=str(e),
                        position=InfoBarPosition.TOP,
                        parent=self,
                    )

        timer = QTimer(self)
        timer.timeout.connect(check_appeal)
        timer.start(100)

    def _on_check_appeals_async(self) -> None:
        """Checks appeal status and reconciles channel health asynchronously."""
        self.btn_check_appeals.setEnabled(False)
        self.btn_check_appeals.setText("🔄 Đang kiểm tra...")

        import concurrent.futures

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self.moderation_service.check_appeal_status, self.profile_id)

        def check_status():
            if future.done():
                timer.stop()
                try:
                    res = future.result()
                    self._load_data()
                    InfoBar.success(
                        title="Đồng Bộ Vé Kháng Cáo Hoàn Tất",
                        content=f"Đã cập nhật {res.get('appeals_count', 0)} vé kháng cáo.",
                        position=InfoBarPosition.TOP,
                        parent=self,
                    )
                except Exception as e:
                    InfoBar.error(
                        title="Lỗi Kiểm Tra Kháng Cáo",
                        content=str(e),
                        position=InfoBarPosition.TOP,
                        parent=self,
                    )
                finally:
                    self.btn_check_appeals.setEnabled(True)
                    self.btn_check_appeals.setText("🔄 Kiểm Tra Tiến Độ Kháng Cáo")

        timer = QTimer(self)
        timer.timeout.connect(check_status)
        timer.start(150)

    def _on_reapply_creator_rewards_async(self) -> None:
        """Submits re-application to Creator Rewards Program asynchronously."""
        self.btn_reapply_creator.setEnabled(False)
        self.btn_reapply_creator.setText("⏳ Đang gửi đơn...")

        import concurrent.futures

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self.moderation_service.submit_creator_rewards_reapply, self.profile_id)

        def check_reapply():
            if future.done():
                timer.stop()
                try:
                    res = future.result()
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
                except Exception as e:
                    InfoBar.error(
                        title="Lỗi Nộp Đơn Quỹ Sáng Tạo",
                        content=str(e),
                        position=InfoBarPosition.TOP,
                        parent=self,
                    )
                finally:
                    self._load_data()

        timer = QTimer(self)
        timer.timeout.connect(check_reapply)
        timer.start(150)

    def _run_scan_async(self) -> None:
        """Executes full moderation scan in background thread."""
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("🔄 Đang quét...")

        import concurrent.futures

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self.moderation_service.scan_full_channel_health, self.profile_id)

        def on_done():
            try:
                res = future.result()
                self._load_data()
                InfoBar.success(
                    title="Quét Sức Khỏe Kênh Hoàn Tất",
                    content=f"Đã cập nhật tình trạng: {res.get('standing', {}).get('status_label', 'OK')} ({res.get('violations_count', 0)} video gậy).",
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
            except Exception as e:
                InfoBar.error(
                    title="Lỗi Quét Sức Khỏe",
                    content=str(e),
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
            finally:
                self.btn_refresh.setEnabled(True)
                self.btn_refresh.setText("⚡ Quét Toàn Kênh")

        poll_timer = QTimer(self)

        def check_status():
            if future.done():
                poll_timer.stop()
                on_done()

        poll_timer.timeout.connect(check_status)
        poll_timer.start(200)


__all__ = ["AccountHealthDialog", "HealthKpiCard"]
