"""
Channel Radar Dialog.
Displays comprehensive TikTok creator account health, traffic quality verdicts,
flop/shadowban warnings, and strategic recommendations in Windows 11 Fluent Design.
"""

from __future__ import annotations

import html
import logging
from datetime import datetime
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
    QScrollArea,
    QVBoxLayout,
    QWidget,
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
from src.domain.analytics.optimal_hours import measured_optimal_schedule
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

logger = logging.getLogger(__name__)


def _load_profile_videos(db_path: Path, profile_id: int) -> list[dict[str, Any]]:
    """Loads video performance history for this profile from statisticTable or videoTables."""
    try:
        with db_session(db_path, write=False) as conn:
            rows = conn.execute(
                """
                SELECT id_video AS video_id, title, views, likes, comments, shares, engagement_rate, date_upload, updated_at
                FROM statisticTable WHERE profile_id = ? ORDER BY id DESC LIMIT 50;
                """,
                (profile_id,),
            ).fetchall()
            if rows:
                return [dict(r) for r in rows]

            # Fallback to videoTables
            v_rows = conn.execute(
                """
                SELECT video_id, title, views, likes, comments, shares, engagement_rate, created_at
                FROM videoTables WHERE profile_id = ? ORDER BY id DESC LIMIT 50;
                """,
                (profile_id,),
            ).fetchall()
            return [dict(r) for r in v_rows]
    except Exception as e:
        logger.warning("Radar video history unreadable for profile %s: %s", profile_id, e)
        return []


def video_posted_hour(video: dict[str, Any]) -> int | None:
    """Local posting hour of a video row (``date_upload`` "YYYY-MM-DD HH:MM:SS"), or None if unknown."""
    raw = video.get("date_upload")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw)).hour
    except ValueError:
        return None


def _html(value: Any) -> str:
    """TikTok-supplied text (titles, names) shown in a rich-text QLabel: never markup."""
    return html.escape(str(value if value is not None else ""))


def _count(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _optimal_hour(profile: dict[str, Any]) -> int | None:
    """TikTok's MEASURED audience-active hour (0-23), if any (the bare ``optimal_hour`` column defaults to 12)."""
    measured = measured_optimal_schedule(profile)
    return measured.hour if measured is not None else None


def load_radar_inputs(
    profile_repo: ProfileRepository, db_path: Path | str, profile_id: int
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Profile row + video history for the radar. Pure DB read: run it off the GUI thread."""
    profile = profile_repo.get_by_id(profile_id) or {}
    return profile, _load_profile_videos(Path(db_path), profile_id)


class ChannelRadarDialog(QDialog):
    """Visual Radar Dialog evaluating TikTok MMO account quality, traffic health, and readiness."""

    def __init__(
        self,
        profile_id: int,
        profile_repo: ProfileRepository,
        videos: list[dict[str, Any]] | None = None,
        db_path: Path | str | None = None,
        parent: QWidget | None = None,
        profile: dict[str, Any] | None = None,
    ) -> None:
        """Pass ``profile`` and ``videos`` from load_radar_inputs() (run off the GUI thread) to keep
        the constructor free of DB I/O; whatever is missing is read synchronously (scripts/tests)."""
        super().__init__(parent)
        self.profile_id = profile_id
        self.profile_repo = profile_repo
        self.db_path = Path(db_path) if db_path else Path("data/app.db")
        self.profile = profile if profile is not None else (self.profile_repo.get_by_id(profile_id) or {})
        self.videos = videos if videos is not None else _load_profile_videos(self.db_path, profile_id)

        self.setWindowTitle("Radar Đánh Giá Sức Khỏe Kênh TikTok MMO")
        self.resize(600, 640)
        self._analyze_and_init_ui()
        fit_dialog_to_content(self)

    def exec(self) -> int:
        """Explicit Python wrapper over QDialog.exec for testability and lifecycle hooks."""
        return super().exec()

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
                    posted_hour=video_posted_hour(v),
                )
            )

        followers = int(self.profile.get("total_followers") or 0)
        views_30d = int(self.profile.get("views_month") or 0)

        report = radar.analyze(
            account_id=str(self.profile_id),
            videos=datapoints,
            followers=followers,
            views_30d=views_30d,
            fallback_best_hour=_optimal_hour(self.profile),
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

        prof_name = (self.profile.get("username_on_tiktok") or self.profile.get("name") or f"Profile #{self.profile_id}").lstrip("@")
        header = create_dialog_header(
            icon=FluentIcon.SPEED_HIGH,
            title=f"Chẩn Đoán Radar Kênh: @{prof_name}",
            subtitle="Đánh giá chất lượng phân phối video, chân dung khán giả, tình báo đối thủ và giờ đăng vàng.",
            parent=self,
        )
        layout.addWidget(header)

        # Scroll Area for rich telemetry content
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content_widget = QWidget()
        c_layout = QVBoxLayout(content_widget)
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.setSpacing(12)

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
        c_layout.addWidget(badge_frame)

        # Grid of Cards
        grp_metrics = QGroupBox("Chỉ Số Sức Khỏe && Thống Kê Tổng Hợp", self)
        style_group_box(grp_metrics)
        grid = QGridLayout(grp_metrics)
        grid.setSpacing(10)

        def make_card(title: str, val: str, kind: str = "info") -> tuple[QFrame, QLabel]:
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
            return card, v_lbl

        c1, _ = make_card("Lượt Theo Dõi", f"{followers:,}")
        c2, _ = make_card("View 30 Ngày", f"{views_30d:,}")
        c3, _ = make_card("Tỷ Lệ Tương Tác", f"{report.signals.engagement_pct:.2f}%", "success")
        grid.addWidget(c1, 0, 0)
        grid.addWidget(c2, 0, 1)
        grid.addWidget(c3, 0, 2)

        c4, _ = make_card("Trung Vị Lượt Xem", f"{int(report.signals.median_views):,}")
        grid.addWidget(c4, 1, 0)

        import json as _json
        measured = measured_optimal_schedule(self.profile)
        peak_users = measured.peak_users if measured is not None else 0
        best_hour_str = measured.window if measured is not None else f"{report.best_posting_hour:02d}:00"

        c5, self.lbl_optimal_hour_stat = make_card("Giờ Đăng Tối Ưu", best_hour_str, "warning")
        if peak_users > 0:
            c5.setToolTip(f"Đỉnh điểm có khoảng ~{peak_users:,} followers đang trực tuyến")
        grid.addWidget(c5, 1, 1)

        alert_kind = "danger" if low_alert.get("alert") else "success"
        alert_text = f"Flop ({low_alert.get('risk_score', 0)}%)" if low_alert.get("alert") else "An Toàn (0%)"
        c6, _ = make_card("Cảnh Báo Flop/Shadowban", alert_text, alert_kind)
        grid.addWidget(c6, 1, 2)

        c_layout.addWidget(grp_metrics)

        # Traffic Source Matrix GroupBox
        ts_raw = self.profile.get("traffic_source_json")
        ts_data: dict[str, Any] = {}
        if ts_raw:
            try:
                ts_data = _json.loads(ts_raw) if isinstance(ts_raw, str) else ts_raw
            except Exception:
                ts_data = {}

        ret_raw = self.profile.get("retention_stats_json")
        ret_data: dict[str, Any] = {}
        if ret_raw:
            try:
                ret_data = _json.loads(ret_raw) if isinstance(ret_raw, str) else ret_raw
            except Exception:
                ret_data = {}

        grp_traffic = QGroupBox("Ma Trận Nguồn View && Chẩn Đoán Phân Phối (Traffic Matrix)", self)
        style_group_box(grp_traffic)
        t_grid = QGridLayout(grp_traffic)
        t_grid.setSpacing(10)

        fyf_val = ts_data.get("for_you")
        fyf_str = f"{fyf_val:.1f}%" if fyf_val is not None else "Chưa có dữ liệu"
        fyf_kind = (
            "success"
            if fyf_val is not None and fyf_val >= 70.0
            else ("warning" if fyf_val is not None and fyf_val >= 20.0 else "danger")
        )
        c_fyf, self.lbl_for_you_stat = make_card("Dành Cho Bạn (FYF)", fyf_str, fyf_kind)
        t_grid.addWidget(c_fyf, 0, 0)

        search_val = ts_data.get("search")
        search_str = f"{search_val:.1f}%" if search_val is not None else "0.0%"
        c_search, _ = make_card("Tìm Kiếm (Search)", search_str, "info")
        t_grid.addWidget(c_search, 0, 1)

        ret_val = ret_data.get("returning_ratio")
        ret_str = f"{ret_val:.1f}%" if ret_val is not None else "Chưa có dữ liệu"
        c_ret, self.lbl_returning_stat = make_card(
            "Fan Quay Lại (Retention)", ret_str, "success" if (ret_val or 0) >= 20.0 else "info"
        )
        t_grid.addWidget(c_ret, 0, 2)

        c_layout.addWidget(grp_traffic)

        # Audience Demographics GroupBox
        demo_raw = self.profile.get("audience_demographics_json")
        if demo_raw:
            try:
                demo_data = _json.loads(demo_raw) if isinstance(demo_raw, str) else demo_raw
                countries = demo_data.get("follower_countries", [])
                ages = demo_data.get("follower_ages", [])
                genders = demo_data.get("follower_genders", [])
                v_total = demo_data.get("viewer_total_7d", 0)

                grp_demo = QGroupBox("Chân Dung Khán Giả && Nhân Khẩu Học (Audience Demographics)", self)
                style_group_box(grp_demo)
                d_lay = QVBoxLayout(grp_demo)
                d_lay.setSpacing(6)

                top_countries_str = ", ".join(f"{_html(c.get('country'))}: {c.get('percentage')}%" for c in countries[:4])
                lbl_c = QLabel(f"• <b>Top Quốc gia xem nhiều:</b> {top_countries_str if top_countries_str else 'Đang cập nhật'}")
                lbl_c.setStyleSheet("font-size: 12px;")
                d_lay.addWidget(lbl_c)

                top_ages_str = ", ".join(f"{_html(a.get('range'))}: {a.get('percentage')}%" for a in ages[:3])
                lbl_a = QLabel(f"• <b>Độ tuổi khán giả:</b> {top_ages_str if top_ages_str else 'Đang cập nhật'}")
                lbl_a.setStyleSheet("font-size: 12px;")
                d_lay.addWidget(lbl_a)

                top_gen_str = ", ".join(f"{_html(g.get('gender'))}: {g.get('percentage')}%" for g in genders[:2])
                viewer_str = f"{v_total:,}" if v_total else "—"
                lbl_g = QLabel(f"• <b>Giới tính:</b> {top_gen_str if top_gen_str else 'Đang cập nhật'} | <b>Tổng người xem 7 ngày:</b> {viewer_str}")
                lbl_g.setStyleSheet("font-size: 12px;")
                d_lay.addWidget(lbl_g)

                c_layout.addWidget(grp_demo)
            except Exception as e_demo:
                logger.debug("Render demographics error: %s", e_demo)

        # Peer Competitor Intelligence GroupBox
        ci_raw = self.profile.get("competitor_intelligence_json")
        if ci_raw:
            try:
                ci_data = _json.loads(ci_raw) if isinstance(ci_raw, str) else ci_raw
                top_c = ci_data.get("top_creators", [])
                top_v = ci_data.get("top_videos", [])
                if top_c or top_v:
                    grp_ci = QGroupBox("Tình Báo Kênh && Video Đối Thủ Khán Giả Quan Tâm", self)
                    style_group_box(grp_ci)
                    ci_lay = QVBoxLayout(grp_ci)
                    ci_lay.setSpacing(6)

                    if top_c:
                        creators_str = " • ".join(
                            f"@{_html(c.get('unique_id'))} ({_count(c.get('follower_count')):,} flw)" for c in top_c[:3]
                        )
                        lbl_cr = QLabel(f"• <b>Kênh đối thủ khán giả cùng xem:</b> {creators_str}")
                        lbl_cr.setStyleSheet("font-size: 12px;")
                        lbl_cr.setWordWrap(True)
                        ci_lay.addWidget(lbl_cr)

                    if top_v:
                        vids_str = " | ".join(
                            f"\"{_html(str(v.get('desc') or '')[:25])}...\" ({_count(v.get('play_count')):,} views)"
                            for v in top_v[:2]
                        )
                        lbl_vr = QLabel(f"• <b>Video viral đối thủ:</b> {vids_str}")
                        lbl_vr.setStyleSheet("font-size: 12px; color: #64748B;")
                        lbl_vr.setWordWrap(True)
                        ci_lay.addWidget(lbl_vr)

                    c_layout.addWidget(grp_ci)
            except Exception as e_ci:
                logger.debug("Render competitor intelligence error: %s", e_ci)

        # Low View Alert Message Box
        if low_alert.get("alert"):
            alert_box = style_card(QFrame(self), kind="warning", object_name="lowViewAlert")
            a_lay = QVBoxLayout(alert_box)
            a_lay.setContentsMargins(12, 10, 12, 10)
            a_lbl = QLabel(str(low_alert.get("message")))
            a_lbl.setWordWrap(True)
            a_lbl.setStyleSheet(f"color: {status_color('warning')}; font-size: 12px; font-weight: 600;")
            a_lay.addWidget(a_lbl)
            c_layout.addWidget(alert_box)

        # Recommendations Box
        grp_recs = QGroupBox("Khuyến Nghị Tối Ưu Hóa Kênh Từ AI / Heuristics", self)
        style_group_box(grp_recs)
        rec_lay = QVBoxLayout(grp_recs)
        for rec in report.recommendations:
            r_lbl = QLabel(f"• {rec}")
            r_lbl.setWordWrap(True)
            r_lbl.setStyleSheet("font-size: 12px; margin-bottom: 4px;")
            rec_lay.addWidget(r_lbl)

        c_layout.addWidget(grp_recs)

        scroll.setWidget(content_widget)
        layout.addWidget(scroll, 1)

        # Footer Buttons
        h_footer = QHBoxLayout()
        h_footer.addStretch()
        self.btn_close = PushButton("Đóng", self)
        self.btn_close.clicked.connect(self.accept)
        h_footer.addWidget(self.btn_close)
        layout.addLayout(h_footer)
