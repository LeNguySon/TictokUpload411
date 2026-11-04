"""TDD Unit Test Suite for Channel Quality Radar Engine.
Conforms to ECC Development Standards.
"""

import pytest
from src.domain.analytics.channel_quality_radar import (
    ChannelQualityRadar,
    ChannelVerdict,
    VideoDataPoint,
)


@pytest.fixture
def radar():
    return ChannelQualityRadar()


def test_channel_quality_radar_empty_videos(radar):
    report = radar.analyze("acc_empty", [], followers=500, views_30d=1000)
    assert report.account_id == "acc_empty"
    assert report.verdict == ChannelVerdict.REAL
    assert report.signals.total_videos == 0
    assert report.signals.total_views == 0


def test_channel_quality_radar_verdict_enough_creator_rewards(radar):
    # 10k followers, 120k views in 30d -> ENOUGH
    videos = [
        VideoDataPoint(video_id="v1", views=40000, likes=3500, comments=210, shares=150, posted_hour=19),
        VideoDataPoint(video_id="v2", views=50000, likes=4200, comments=310, shares=200, posted_hour=20),
        VideoDataPoint(video_id="v3", views=35000, likes=2900, comments=180, shares=110, posted_hour=19),
    ]

    report = radar.analyze("acc_crp", videos, followers=12500, views_30d=125000)
    assert report.verdict == ChannelVerdict.ENOUGH
    assert report.signals.total_views == 125000
    assert report.signals.views_per_video > 40000
    assert report.signals.engagement_pct > 8.0
    assert report.best_posting_hour == 20
    assert any("Creator Rewards" in rec for rec in report.recommendations)


def test_channel_quality_radar_verdict_buff_artificial(radar):
    # Abnormally high views but almost 0 engagement (< 0.2%)
    videos = [
        VideoDataPoint(video_id="b1", views=80000, likes=50, comments=2, shares=1, posted_hour=3),
        VideoDataPoint(video_id="b2", views=95000, likes=60, comments=1, shares=0, posted_hour=3),
        VideoDataPoint(video_id="b3", views=75000, likes=40, comments=0, shares=0, posted_hour=3),
    ]

    report = radar.analyze("acc_bot", videos, followers=200, views_30d=5000)
    assert report.verdict == ChannelVerdict.BUFF
    assert report.signals.engagement_pct < 0.2
    assert any("buff" in rec.lower() or "bot" in rec.lower() for rec in report.recommendations)


def test_channel_quality_radar_verdict_real_organic(radar):
    # Organic reach with healthy 5% engagement
    videos = [
        VideoDataPoint(video_id="r1", views=5000, likes=300, comments=25, shares=15, posted_hour=12),
        VideoDataPoint(video_id="r2", views=8000, likes=520, comments=40, shares=25, posted_hour=18),
        VideoDataPoint(video_id="r3", views=6000, likes=410, comments=35, shares=18, posted_hour=18),
    ]

    report = radar.analyze("acc_real", videos, followers=3500, views_30d=19000)
    assert report.verdict == ChannelVerdict.REAL
    assert report.signals.engagement_pct > 6.0
    assert report.best_posting_hour == 18
