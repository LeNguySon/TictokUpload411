"""
AccountHealthDialog — Giao diện Kiểm tra Chất lượng Tài khoản, Gậy Vi phạm & Gậy Nguyên tác TikTok.
Learned from Gloglin2609/ui/views/account_health_dialog.py with Windows 11 Fluent UI dark styling.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from PyQt6.QtCore import QThreadPool
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import InfoBar, InfoBarPosition

from src.infrastructure.tiktok.moderation_service import TikTokModerationService


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
        self.value_label.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: bold;")
        layout.addWidget(self.value_label)

    def set_value(self, value_text: str, color: str = "#F1F5F9") -> None:
        self.value_label.setText(value_text)
        self.value_label.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: bold;")


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
        self.thread_pool = QThreadPool.globalInstance()

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
        self.setMinimumSize(780, 520)
        self.resize(960, 680)

        self._build_ui()
        self._load_data()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # 1. Header Title & Actions
        title_row = QHBoxLayout()
        self.lbl_title = QLabel(f"🛡️ Sức Khỏe Kênh & Gậy Vi Phạm TikTok — Profile #{self.profile_id}")
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #F1F5F9;")
        title_row.addWidget(self.lbl_title)
        title_row.addStretch(1)

        self.btn_refresh = QPushButton("🔄 Quét Sức Khỏe & Gậy Vi Phạm")
        self.btn_refresh.setStyleSheet(
            "background-color: #0284C7; color: white; padding: 6px 14px; border-radius: 6px; font-weight: bold;"
        )
        self.btn_refresh.clicked.connect(self._run_scan_async)
        title_row.addWidget(self.btn_refresh)
        layout.addLayout(title_row)

        # 2. 4 KPI Status Cards
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(10)

        self.card_standing = HealthKpiCard("CHẤT LƯỢNG TÀI KHOẢN", "Chưa xác minh", "#64748B")
        self.card_strikes = HealthKpiCard("GẬY VI PHẠM TÍCH LŨY", "—", "#64748B")
        self.card_penalty = HealthKpiCard("ĐIỂM PHẠT TOÀN KÊNH", "0 đ", "#64748B")
        self.card_shadowban = HealthKpiCard("ƯỚC TÍNH RỦI RO CỤC BỘ", "Bình thường", "#10B981")

        cards_layout.addWidget(self.card_standing)
        cards_layout.addWidget(self.card_strikes)
        cards_layout.addWidget(self.card_penalty)
        cards_layout.addWidget(self.card_shadowban)
        layout.addLayout(cards_layout)

        # 3. Diagnostic Banner
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

        # 4. Tabs: Video Vi Phạm & Quản lý
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        # Tab 1: Video Vi phạm & Gậy nguyên tác
        tab_violate = QWidget()
        v_layout = QVBoxLayout(tab_violate)
        v_layout.setContentsMargins(6, 10, 6, 6)

        self.table_violate = QTableWidget(0, 5)
        self.table_violate.setHorizontalHeaderLabels(
            ["Video ID", "Tiêu đề video", "Loại gậy vi phạm", "Hạn nộp đơn kháng cáo", "Trạng thái"]
        )
        self.table_violate.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_violate.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_violate.setAlternatingRowColors(True)
        self.table_violate.verticalHeader().setVisible(False)
        v_layout.addWidget(self.table_violate)
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
        a_layout.addWidget(self.table_appeals)
        self.tabs.addTab(tab_appeals, "📝 Lịch Sử Vé Kháng Cáo (Appeals)")

    def _load_data(self) -> None:
        """Loads profile health and video violations directly from SQLite database."""
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

            # Update KPI Cards
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
                self.card_shadowban.set_value("Có dấu hiệu Shadowban", "#EF4444")
            else:
                self.card_shadowban.set_value("Bình thường (FYF OK)", "#10B981")

            # Update Diagnostic Content
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

            # Load violateVideos
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
                st_item = QTableWidgetItem("Chờ giải trình" if st_text == "pending" else st_text)
                self.table_violate.setItem(row_idx, 4, st_item)

            # Load accountAppeals
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

    def _run_scan_async(self) -> None:
        """Executes full moderation scan in background thread."""
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("🔄 Đang quét TikTok API...")

        class ScanWorker(QWidget):
            def __init__(self, service: TikTokModerationService, profile_id: int):
                super().__init__()
                self.service = service
                self.profile_id = profile_id

        def do_scan():
            res = self.moderation_service.scan_full_channel_health(self.profile_id)
            return res

        import concurrent.futures

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(do_scan)

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
                self.btn_refresh.setText("🔄 Quét Sức Khỏe & Gậy Vi Phạm")

        # Check future completion via timer
        from PyQt6.QtCore import QTimer

        poll_timer = QTimer(self)

        def check_status():
            if future.done():
                poll_timer.stop()
                on_done()

        poll_timer.timeout.connect(check_status)
        poll_timer.start(200)


__all__ = ["AccountHealthDialog", "HealthKpiCard"]
