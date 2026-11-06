"""
Unit tests for Advanced Creator Telemetry, Traffic Source Matrix, Shadowban Diagnostics,
Optimal Posting Hours, and Pre-publish Content Check (Strict TDD Suite).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from src.domain.licensing import entitlements
from src.domain.licensing.claims import LicenseClaims
from src.domain.licensing.plans import Plan
from src.infrastructure.database.connection import get_db_connection
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.tiktok.moderation_service import TikTokModerationService
from src.infrastructure.tiktok.network_sniffer import TikTokNetworkSniffer
from src.presentation.dialogs.channel_radar_dialog import ChannelRadarDialog


@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    db_file = tmp_path / "test_advanced_insights.db"
    run_all_migrations(db_file)
    conn = get_db_connection(db_file)
    conn.execute(
        """
        INSERT INTO proxies (id, host, port, protocol, proxy_type, status)
        VALUES (1, '127.0.0.1', 8080, 'http', 'static', 'alive');
        """
    )
    conn.execute(
        """
        INSERT INTO profiles (
            id, uuid, name, username_on_tiktok, proxy_id, storage_dir, status, user_agent,
            total_followers, total_likes, total_videos, views_month, total_views,
            cookies_json
        ) VALUES (
            78, 'uuid-78', 'swall.pain', '@swall.pain', 1, 'profiles/swall.pain', 'LIVE', 'Mozilla/5.0',
            13468, 92227, 79, 338360, 338360,
            '[{"name":"sessionid","value":"test_session_123","domain":".tiktok.com"}]'
        );
        """
    )
    conn.commit()
    conn.close()
    return db_file


def test_sniffer_parses_traffic_source_matrix_and_safe_shadowban(test_db: Path) -> None:
    sniffer = TikTokNetworkSniffer(db_path=test_db)
    sample_overview = {
        "analytics_overview_traffic_source": {
            "key_value": [
                {"key": "For You", "value": 0.961},
                {"key": "Search", "value": 0.030},
                {"key": "Personal profile", "value": 0.007},
                {"key": "Following", "value": 0.002},
            ]
        }
    }
    handled = sniffer.process_api_response(
        78,
        "https://www.tiktok.com/tiktok/v1/analytics/insights/",
        sample_overview,
    )
    assert handled is True

    conn = get_db_connection(test_db)
    row = conn.execute("SELECT traffic_source_json, shadowban_status, shadowban_reasons FROM profiles WHERE id=78").fetchone()
    conn.close()

    assert row["traffic_source_json"] is not None
    ts_data = json.loads(row["traffic_source_json"])
    assert ts_data["for_you"] == 96.1
    assert ts_data["search"] == 3.0
    assert ts_data["profile"] == 0.7
    assert ts_data["following"] == 0.2
    assert row["shadowban_status"] == "safe"


def test_sniffer_detects_shadowban_when_for_you_crashes(test_db: Path) -> None:
    sniffer = TikTokNetworkSniffer(db_path=test_db)
    crashed_overview = {
        "analytics_overview_traffic_source": {
            "key_value": [
                {"key": "For You", "value": 0.04},  # Only 4% FYF
                {"key": "Personal profile", "value": 0.85},
                {"key": "Following", "value": 0.11},
            ]
        }
    }
    handled = sniffer.process_api_response(
        78,
        "https://www.tiktok.com/tiktok/v1/analytics/insights/",
        crashed_overview,
    )
    assert handled is True

    conn = get_db_connection(test_db)
    row = conn.execute("SELECT shadowban_status, shadowban_reasons FROM profiles WHERE id=78").fetchone()
    conn.close()

    assert row["shadowban_status"] == "shadowban"
    assert "Dành cho bạn (FYF) tụt dưới 20%" in (row["shadowban_reasons"] or "")


def test_sniffer_parses_viewer_active_hours_and_sets_optimal_hour(test_db: Path) -> None:
    sniffer = TikTokNetworkSniffer(db_path=test_db)
    # Peak at hour 22 with 16802 viewers
    hourly_values = [{"key": str(h), "value": 1000 + (15000 if h == 22 else h * 100)} for h in range(24)]
    sample_overview = {
        "analytics_viewer_active_hours": {
            "list": [
                {"key": "20261029", "list": {"key_value": hourly_values}}
            ]
        }
    }
    handled = sniffer.process_api_response(
        78,
        "https://www.tiktok.com/tiktok/v1/analytics/insights/",
        sample_overview,
    )
    assert handled is True

    conn = get_db_connection(test_db)
    row = conn.execute("SELECT optimal_hour FROM profiles WHERE id=78").fetchone()
    conn.close()

    assert row["optimal_hour"] == 22


def test_sniffer_parses_retention_and_new_vs_returning_viewers(test_db: Path) -> None:
    sniffer = TikTokNetworkSniffer(db_path=test_db)
    sample_insight = {
        "new_viewer": [
            {"days_before_today": -1, "status": 0, "value": 30000},
            {"days_before_today": -2, "status": 0, "value": 30000},
        ],
        "returning_viewer": [
            {"days_before_today": -1, "status": 0, "value": 10000},
            {"days_before_today": -2, "status": 0, "value": 10000},
        ],
    }
    handled = sniffer.process_api_response(
        78,
        "https://www.tiktok.com/aweme/v2/data/insight/?aid=1988",
        sample_insight,
    )
    assert handled is True

    conn = get_db_connection(test_db)
    row = conn.execute("SELECT retention_stats_json FROM profiles WHERE id=78").fetchone()
    conn.close()

    assert row["retention_stats_json"] is not None
    ret = json.loads(row["retention_stats_json"])
    assert ret["total_new"] == 60000
    assert ret["total_returning"] == 20000
    assert ret["returning_ratio"] == 25.0


def test_moderation_service_precheck_content_safe(test_db: Path) -> None:
    entitlements.set_current(LicenseClaims(
        lid="lic-pro", sub="test", plan=Plan.PRO, iat=1000, exp=9999999999, mid="mid", kid="kid"
    ))
    mod_svc = TikTokModerationService(db_path=test_db)

    mock_resp = {
        "status_code": 0,
        "check_result": {
            "has_violation": False,
            "copyright_risk": "low",
            "audio_status": "clear",
            "message": "Nội dung an toàn, không phát hiện vi phạm bản quyền hoặc nguyên tắc.",
        }
    }

    with patch.object(mod_svc, "_request_tiktok_api", return_value=mock_resp):
        res = mod_svc.precheck_video_content(profile_id=78, video_title="My Viral Meme")

    assert res["is_safe"] is True
    assert res["copyright_risk"] == "low"
    assert "Nội dung an toàn" in res["message"]


def test_channel_radar_dialog_displays_traffic_matrix_and_optimal_hour(test_db: Path, qtbot) -> None:
    conn = get_db_connection(test_db)
    conn.execute(
        """
        UPDATE profiles SET
            traffic_source_json = '{"for_you": 96.1, "search": 3.0, "profile": 0.7, "following": 0.2}',
            optimal_hour = 22,
            retention_stats_json = '{"total_new": 60000, "total_returning": 20000, "returning_ratio": 25.0}'
        WHERE id = 78;
        """
    )
    conn.commit()
    conn.close()

    repo = ProfileRepository(test_db)
    dlg = ChannelRadarDialog(profile_id=78, profile_repo=repo, db_path=test_db)
    qtbot.addWidget(dlg)

    # Check that Traffic Matrix elements are present
    assert hasattr(dlg, "lbl_for_you_stat")
    assert "96.1%" in dlg.lbl_for_you_stat.text()
    assert hasattr(dlg, "lbl_optimal_hour_stat")
    assert "22:00" in dlg.lbl_optimal_hour_stat.text()
    assert hasattr(dlg, "lbl_returning_stat")
    assert "25.0%" in dlg.lbl_returning_stat.text()
