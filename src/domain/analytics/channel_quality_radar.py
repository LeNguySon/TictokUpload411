"""
Channel Quality Radar — TikTok Account Health & Traffic Quality Analyzer.
Learned from Gloglin2609/engine/tiktok/channel_quality_radar.py.

Evaluates channel health and traffic validity based on statistical signals:
- engagement_pct: (Likes + Comments + Shares + Saves) / Views * 100%
- hours_cv: Coefficient of variation of posting hours
- views_per_video: Average views per video across analyzed window
- median_views: Median view baseline

Outputs Verdicts:
- REAL: Organic reach driven primarily by TikTok For You feed (FYF).
- BUFF: Artificial / bot-farmed views (high views, low engagement).
- ADS: Paid promotion / Spark Ads.
- ENOUGH: Eligible for Creator Rewards Program (>=10k followers & >=100k views/30d).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ChannelVerdict(StrEnum):
    REAL = "real"
    BUFF = "buff"
    ADS = "ads"
    ENOUGH = "enough"


@dataclass
class VideoDataPoint:
    video_id: str
    views: int
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    duration_secs: float = 30.0
    posted_hour: int | None = None  # local hour the video was posted; None = unknown
    for_you_pct: float = 0.0


@dataclass
class QualitySignals:
    engagement_pct: float
    hours_cv: float
    views_per_video: float
    total_views: int
    total_videos: int
    median_views: float


@dataclass
class ChannelQualityReport:
    account_id: str
    verdict: ChannelVerdict
    confidence: float
    signals: QualitySignals
    best_posting_hour: int
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "verdict": self.verdict.value,
            "confidence": round(self.confidence, 2),
            "signals": {
                "engagement_pct": round(self.signals.engagement_pct, 2),
                "hours_cv": round(self.signals.hours_cv, 2),
                "views_per_video": round(self.signals.views_per_video, 1),
                "total_views": self.signals.total_views,
                "total_videos": self.signals.total_videos,
                "median_views": round(self.signals.median_views, 1),
            },
            "best_posting_hour": self.best_posting_hour,
            "recommendations": self.recommendations,
        }


class ChannelQualityRadar:
    """Advanced statistical analyzer evaluating channel health, traffic, and monetization readiness."""

    def analyze(
        self,
        account_id: str,
        videos: list[VideoDataPoint],
        followers: int = 0,
        views_30d: int = 0,
        fallback_best_hour: int | None = None,
    ) -> ChannelQualityReport:
        """``fallback_best_hour`` (e.g. TikTok's audience-active hour) is used when no video has a known posting hour."""
        if not videos:
            empty_signals = QualitySignals(
                engagement_pct=0.0,
                hours_cv=0.0,
                views_per_video=0.0,
                total_views=0,
                total_videos=0,
                median_views=0.0,
            )
            return ChannelQualityReport(
                account_id=account_id,
                verdict=ChannelVerdict.REAL,
                confidence=0.5,
                signals=empty_signals,
                best_posting_hour=fallback_best_hour if fallback_best_hour is not None else 19,
                recommendations=["Chưa có dữ liệu video để phân tích chuyên sâu."],
            )

        n = len(videos)
        total_views = sum(v.views for v in videos)
        total_likes = sum(v.likes for v in videos)
        total_comments = sum(v.comments for v in videos)
        total_shares = sum(v.shares for v in videos)
        total_saves = sum(v.saves for v in videos)

        # 1. Engagement Rate
        engagement_pct = (
            ((total_likes + total_comments + total_shares + total_saves) / total_views * 100.0)
            if total_views > 0
            else 0.0
        )

        # 2. Average Views Per Video
        views_per_video = total_views / n if n > 0 else 0.0

        # 3. Hours Coefficient of Variation
        hours = [v.posted_hour for v in videos if v.posted_hour is not None]
        mean_hour = sum(hours) / len(hours) if hours else 0.0
        if len(hours) > 1 and mean_hour > 0:
            variance_hour = sum((h - mean_hour) ** 2 for h in hours) / (len(hours) - 1)
            hours_cv = math.sqrt(variance_hour) / mean_hour
        else:
            hours_cv = 0.0

        # 4. Median Views
        sorted_views = sorted(v.views for v in videos)
        median_views = sorted_views[n // 2] if n % 2 != 0 else (sorted_views[n // 2 - 1] + sorted_views[n // 2]) / 2.0

        signals = QualitySignals(
            engagement_pct=engagement_pct,
            hours_cv=hours_cv,
            views_per_video=views_per_video,
            total_views=total_views,
            total_videos=n,
            median_views=median_views,
        )

        verdict, confidence, recs = self._compute_verdict(signals, videos, followers, views_30d)
        best_hour = self._compute_best_posting_hour(videos, fallback_best_hour)

        return ChannelQualityReport(
            account_id=account_id,
            verdict=verdict,
            confidence=confidence,
            signals=signals,
            best_posting_hour=best_hour,
            recommendations=recs,
        )

    def _compute_verdict(
        self,
        signals: QualitySignals,
        videos: list[VideoDataPoint],
        followers: int,
        views_30d: int,
    ) -> tuple[ChannelVerdict, float, list[str]]:
        recs: list[str] = []

        # 1. Creator Rewards Threshold Check
        if followers >= 10000 and views_30d >= 100000:
            recs.append("Kênh đã đủ điều kiện bật kiếm tiền Creator Rewards Program (>=10k sub & >=100k views/30d)!")
            recs.append("Duy trì nhịp đăng đều đặn vào khung giờ vàng để tối ưu hóa RPM.")
            return ChannelVerdict.ENOUGH, 0.95, recs

        # 2. Artificial / Bot Buff Check
        if signals.views_per_video > 10000 and signals.engagement_pct < 0.5:
            recs.append(
                "Cảnh báo: Tỷ lệ tương tác cực thấp so với lượt xem. Nghi vấn kênh bị buff view ảo hoặc chạy bot."
            )
            recs.append("Cần dừng ngay các công cụ buff để tránh bị thuật toán TikTok shadowban.")
            return ChannelVerdict.BUFF, 0.88, recs

        # 3. Organic Reach Check
        if signals.engagement_pct >= 2.0:
            recs.append("Tỷ lệ tương tác tự nhiên lành mạnh (> 2%).")
            recs.append("Nên tăng cường kêu gọi bình luận và chia sẻ trong 3 giây đầu video.")
        else:
            recs.append("Tương tác ở mức trung bình. Hãy sử dụng hook hấp dẫn hơn để tăng like và save.")

        return ChannelVerdict.REAL, 0.80, recs

    def _compute_best_posting_hour(self, videos: list[VideoDataPoint], fallback: int | None = None) -> int:
        hour_views: dict[int, list[int]] = {}
        for v in videos:
            if v.posted_hour is not None:
                hour_views.setdefault(v.posted_hour, []).append(v.views)

        best_hour = fallback if fallback is not None else 19
        best_avg = -1.0
        for h, v_list in hour_views.items():
            avg = sum(v_list) / len(v_list)
            if avg > best_avg:
                best_avg = avg
                best_hour = h

        return best_hour
