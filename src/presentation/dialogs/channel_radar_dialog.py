"""
Channel Radar Dialog.
Displays comprehensive TikTok creator account health, traffic quality verdicts,
flop/shadowban warnings, and strategic recommendations in Windows 11 Fluent Design.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)
from qfluentwidgets import (
    FluentIcon,
    PushButton,
)

from src.domain.analytics.channel_quality_radar import (
    ChannelQualityRadar,
    ChannelVerdict,
    VideoDataPoint,
)
from src.domain.analytics.low_view_alert import analyze_low_view_alert
from src.infrastructure.database.connection import db_session
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.presentation.dialogs.dialog_helpers import (
    STANDARD_DIALOG_MARGINS,
    STANDARD_DIALOG_SPACING,
    create_dialog_header,
    fit_dialog_to_content,
    status_color,
    style_card,
    style_group_box,
)


class ChannelRadarDialog(QDialog):
    """Visual Radar Dialog evaluating TikTok MMO account quality, traffic health, and readiness."""

    def __init__(
        self,
        profile_id: int,
        profile_repo: ProfileRepository,
        videos: list[dict[str, Any]] | None = None,
        db_path: Path | str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.profile_id = profile_id
        self.profile_repo = profile_repo
        self.db_path = Path(db_path) if db_path else Path("data/app.db")
        self.profile = self.profile_repo.get_by_id(profile_id) or {}
        self.videos = videos if videos is not None else self._load_profile_videos()

        self.setWindowTitle("Radar Đánh Giá Sức Khỏe Kênh TikTok MMO")
        self.resize(600, 640)
        self._analyze_and_init_ui()
        fit_dialog_to_content(self)

    def exec(self) -> int:
        """Explicit Python wrapper over QDialog.exec for testability and lifecycle hooks."""
        return super().exec()

    def _load_profile_videos(self) -> list[dict[str, Any]]:
        """Loads video performance history for this profile from statisticTable or videoTables."""
        try:
            with db_session(self.db_path, write=False) as conn:
                rows = conn.execute(
                    """
                    SELECT id_video AS video_id, title, views, likes, comments, shares, engagement_rate, updated_at
                    FROM statisticTable WHERE profile_id = ? ORDER BY id DESC LIMIT 50;
                    """,
                    (self.profile_id,),
                ).fetchall()
                if rows:
                    return [dict(r) for r in rows]

                # Fallback to videoTables
                v_rows = conn.execute(
                    """
                    SELECT video_id, title, views, likes, comments, shares, engagement_rate, created_at
                    FROM videoTables WHERE profile_id = ? ORDER BY id DESC LIMIT 50;
                    """,
                    (self.profile_id,),
                ).fetchall()
                return [dict(r) for r in v_rows]
        except Exception:
            return []

    def _analyze_and_init_ui(self) -> None:
        # 1. Run ChannelQualityRadar
        radar = ChannelQualityRadar()
        datapoints = []
        for v in self.videos:
            datapoints.append(
                VideoDataPoint(
                    video_id=str(v.get("video_id") or ""),
                    views=int(v.get("views") or 0),
                    likes=int(v.get("likes") or 0),
                    comments=int(v.get("comments") or 0),
                    shares=int(v.get("shares") or 0),
                )
            )

        followers = int(self.profile.get("total_followers") or 0)
        views_30d = int(self.profile.get("views_month") or 0)

        report = radar.analyze(
            account_id=str(self.profile_id),
            videos=datapoints,
            followers=followers,
            views_30d=views_30d,
        )
        self.report = report
        self.recommendations = report.recommendations

        # 2. Run LowViewAlert
        low_alert = analyze_low_view_alert(self.videos)
        self.low_alert = low_alert

        # 3. Build UI
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*STANDARD_DIALOG_MARGINS)
        layout.setSpacing(STANDARD_DIALOG_SPACING)

        prof_name = self.profile.get("username_on_tiktok") or self.profile.get("name") or f"Profile #{self.profile_id}"
        header = create_dialog_header(
            icon=FluentIcon.SPEED_HIGH,
            title=f"Chẩn Đoán Radar Kênh: @{prof_name}",
            subtitle="Đánh giá chất lượng phân phối video, cảnh báo flop/view ảo và tư vấn chiến lược nội dung.",
            parent=self,
        )
        layout.addWidget(header)

        # Verdict Badge
        badge_frame = QFrame(self)
        badge_layout = QHBoxLayout(badge_frame)
        badge_layout.setContentsMargins(12, 10, 12, 10)

        self.lbl_verdict_badge = QLabel(self)
        self.lbl_verdict_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if report.verdict == ChannelVerdict.ENOUGH:
            verdict_text, verdict_kind = "ĐỦ ĐIỀU KIỆN BẬT KIẾM TIỀN (CRP ELIGIBLE)", "warning"
        elif report.verdict == ChannelVerdict.BUFF:
            verdict_text, verdict_kind = "NGHI NGỜ BUFF VIEW ẢO (LOW ENGAGEMENT)", "danger"
        else:
            verdict_text, verdict_kind = "PHÂN PHỐI TỰ NHIÊN (ORGANIC REACH)", "success"
        self.lbl_verdict_badge.setText(verdict_text)
        self.lbl_verdict_badge.setStyleSheet(
            f"font-weight: 600; font-size: 14px; color: {status_color(verdict_kind)}; background: transparent;"
        )
        style_card(badge_frame, kind=verdict_kind, object_name="verdictBadge")

        badge_layout.addWidget(self.lbl_verdict_badge)
        layout.addWidget(badge_frame)

        # Grid of Cards
        grp_metrics = QGroupBox("Chỉ Số Sức Khỏe && Thống Kê Tổng Hợp", self)
        style_group_box(grp_metrics)
        grid = QGridLayout(grp_metrics)
        grid.setSpacing(10)

        def make_card(title: str, val: str, kind: str = "info") -> QFrame:
            card = style_card(QFrame(), object_name="metricCard")
            c_lay = QVBoxLayout(card)
            c_lay.setContentsMargins(12, 8, 12, 8)
            c_lay.setSpacing(2)
            t_lbl = QLabel(title)
            t_lbl.setStyleSheet(f"font-size: 11px; color: {status_color('neutral')};")
            v_lbl = QLabel(val)
            v_lbl.setStyleSheet(f"font-size: 16px; font-weight: 600; color: {status_color(kind)};")
            c_lay.addWidget(t_lbl)
            c_lay.addWidget(v_lbl)
            return card

        grid.addWidget(make_card("Lượt Theo Dõi", f"{followers:,}"), 0, 0)
        grid.addWidget(make_card("View 30 Ngày", f"{views_30d:,}"), 0, 1)
        grid.addWidget(make_card("Tỷ Lệ Tương Tác", f"{report.signals.engagement_pct:.2f}%", "success"), 0, 2)
        grid.addWidget(make_card("Trung Vị Lượt Xem", f"{int(report.signals.median_views):,}"), 1, 0)
        grid.addWidget(make_card("Giờ Đăng Tối Ưu", f"{report.best_posting_hour}:00", "warning"), 1, 1)

        alert_kind = "danger" if low_alert.get("alert") else "success"
        alert_text = f"Flop ({low_alert.get('risk_score', 0)}%)" if low_alert.get("alert") else "An Toàn (0%)"
        grid.addWidget(make_card("Cảnh Báo Flop/Shadowban", alert_text, alert_kind), 1, 2)

        layout.addWidget(grp_metrics)

        # Low View Alert Message Box
        if low_alert.get("alert"):
            alert_box = style_card(QFrame(self), kind="warning", object_name="lowViewAlert")
            a_lay = QVBoxLayout(alert_box)
            a_lay.setContentsMargins(12, 10, 12, 10)
            a_lbl = QLabel(str(low_alert.get("message")))
            a_lbl.setWordWrap(True)
            a_lbl.setStyleSheet(f"color: {status_color('warning')}; font-size: 12px; font-weight: 600;")
            a_lay.addWidget(a_lbl)
            layout.addWidget(alert_box)

        # Recommendations Box
        grp_recs = QGroupBox("Khuyến Nghị Tối Ưu Hóa Kênh Từ AI / Heuristics", self)
        style_group_box(grp_recs)
        rec_lay = QVBoxLayout(grp_recs)
        for rec in report.recommendations:
            r_lbl = QLabel(f"• {rec}")
            r_lbl.setWordWrap(True)
            r_lbl.setStyleSheet("font-size: 12px; margin-bottom: 4px;")
            rec_lay.addWidget(r_lbl)

        layout.addWidget(grp_recs)

        # Footer Buttons
        h_footer = QHBoxLayout()
        h_footer.addStretch()
        self.btn_close = PushButton("Đóng", self)
        self.btn_close.clicked.connect(self.accept)
        h_footer.addWidget(self.btn_close)
        layout.addLayout(h_footer)
