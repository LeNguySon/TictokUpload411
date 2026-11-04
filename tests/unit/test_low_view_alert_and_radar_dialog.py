"""TDD Unit Test Suite for Low View Alert Engine and Channel Radar Dialog.
Conforms to ECC Development Standards.
"""

from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication
from src.domain.analytics.low_view_alert import analyze_low_view_alert
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.presentation.dialogs.channel_radar_dialog import ChannelRadarDialog


@pytest.fixture
def app_instance():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


@pytest.fixture
def db_env(tmp_path: Path):
    db_file = tmp_path / "radar_dialog_test.db"
    run_all_migrations(db_file)
    repo = ProfileRepository(db_file)
    return {
        "db_file": db_file,
        "repo": repo,
        "tmp_path": tmp_path,
    }


def test_analyze_low_view_alert_detects_consecutive_flop():
    # Historical videos: 10 videos with ~1000 views
    # 5 newest videos: all have < 50 views (< 10% median and < 100)
    videos = []
    base_time = 1718000000

    # 5 newest videos (consecutive flop)
    for i in range(5):
        videos.append(
            {
                "video_id": f"flop_{i}",
                "views": 25 + i * 5,  # 25, 30, 35, 40, 45 (< 100)
                "date_upload": base_time + (20 - i) * 3600,
            }
        )

    # 5 older videos with healthy views
    for i in range(5):
        videos.append(
            {
                "video_id": f"good_{i}",
                "views": 1200 + i * 50,  # ~1300
                "date_upload": base_time + i * 3600,
            }
        )

    res = analyze_low_view_alert(videos)
    assert res["ok"] is True
    assert res["alert"] is True
    assert res["coverage"]["consecutive_low_views"] == 5
    assert res["risk_score"] >= 50.0
    assert "dưới 10% trung vị" in res["message"]


def test_analyze_low_view_alert_healthy_channel():
    videos = [
        {"video_id": f"vid_{i}", "views": 2500 + i * 100, "date_upload": 1718000000 + i * 3600} for i in range(10)
    ]
    res = analyze_low_view_alert(videos)
    assert res["ok"] is True
    assert res["alert"] is False
    assert res["coverage"]["consecutive_low_views"] == 0


def test_channel_radar_dialog_ui(app_instance, db_env):
    repo: ProfileRepository = db_env["repo"]
    pid = repo.create(
        {
            "name": "RadarTarget",
            "total_followers": 15000,
            "views_month": 180000,
            "status": "LIVE",
        }
    )

    sample_videos = [
        {"video_id": "v1", "views": 50000, "likes": 4000, "comments": 300, "shares": 200, "created_at": "2026-10-01"},
        {"video_id": "v2", "views": 70000, "likes": 5500, "comments": 450, "shares": 350, "created_at": "2026-10-02"},
        {"video_id": "v3", "views": 60000, "likes": 4800, "comments": 380, "shares": 250, "created_at": "2026-10-03"},
    ]

    dialog = ChannelRadarDialog(
        profile_id=pid,
        profile_repo=repo,
        videos=sample_videos,
    )

    assert dialog.profile_id == pid
    assert (
        "ĐỦ ĐIỀU KIỆN" in dialog.lbl_verdict_badge.text().upper() or "CRP ELIGIBLE" in dialog.lbl_verdict_badge.text()
    )
    assert len(dialog.recommendations) > 0
