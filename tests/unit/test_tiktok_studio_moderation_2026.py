"""Unit tests for TikTok Studio 2026 Telemetry, RPM, and Moderation Services.
Validates parity with authentic TikTok Studio endpoints:
- POST /tiktok/creator/manage/item_list/v1/
- GET /mod/v1/getPenaltyDetails/?vid=...
- GET /tiktok/v1/analytics/insights/
- POST /tiktokstudio/api/web/counter/getHashCount
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from src.domain.licensing import entitlements
from src.infrastructure.database.connection import get_db_connection
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.tiktok.moderation_service import TikTokModerationService
from src.infrastructure.tiktok.passive_sync_service import PassiveTikTokSyncService


@pytest.fixture(autouse=True)
def allow_channel_health():
    """Bypasses licensing check for unit tests."""
    with patch.object(entitlements, "require", return_value=None):
        yield


@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    db_file = tmp_path / "test_studio_2026.db"
    run_all_migrations(db_file)
    conn = get_db_connection(db_file)
    conn.execute(
        """
        INSERT INTO proxies (id, host, port, protocol, status)
        VALUES (1, '127.0.0.1', 8080, 'http', 'alive')
        """
    )
    conn.execute(
        """
        INSERT INTO profiles (
            id, uuid, name, username_on_tiktok, status, cookies_json, user_agent, storage_dir, proxy_id
        ) VALUES (
            78, 'prof-uuid-78', 'swall.pain', 'swall.pain', 'LIVE', 'sessionid=test_sess; tt_csrf_token=test_csrf',
            'Mozilla/5.0 TestChrome', 'profiles/swall.pain', 1
        )
        """
    )
    conn.commit()
    conn.close()
    return db_file


def test_fetch_account_standing_with_2026_counter_and_strikes(test_db: Path):
    """Verifies fetch_account_standing uses getHashCount (total_item_count vs item_count) and strikes."""
    service = TikTokModerationService(db_path=test_db)

    # Mock client requests
    def mock_request_api(profile_id, url, **kwargs):
        if "gethashcount" in url.lower():
            return {
                "status_code": 0,
                "item_count": 79,
                "total_item_count": 246,
                "like_count": 92267,
                "visitor_count": 4674,
            }
        return {"status_code": 0}

    with patch.object(service.client, "request_api", side_effect=mock_request_api):
        res = service.fetch_account_standing(profile_id=78)

    assert res["ok"] is True
    assert res["profile_id"] == 78
    assert res["public_items"] == 79
    assert res["total_items"] == 246
    assert res["removed_items"] == 167

    # Check persistence in DB
    conn = get_db_connection(test_db)
    row = conn.execute("SELECT total_videos, account_standing, strike_count FROM profiles WHERE id=78").fetchone()
    conn.close()
    assert row["total_videos"] == 79
    assert row["account_standing"] is not None


def test_fetch_video_violations_with_get_penalty_details(test_db: Path):
    """Verifies fetch_video_violations calls item_list_v1 and getPenaltyDetails to detect real strikes."""
    service = TikTokModerationService(db_path=test_db)

    def mock_request_api(profile_id, url, **kwargs):
        url_lower = url.lower()
        if "item_list/v1" in url_lower:
            return {
                "status_code": 0,
                "item_list": [
                    {
                        "item_id": "7680361725085945110",
                        "desc": "#fyp #shorts",
                        "create_time": "1788800000",
                        "status": 102,
                    },
                    {
                        "item_id": "7677402397957737750",
                        "desc": "Normal video",
                        "create_time": "1787534570",
                        "status": 102,
                    },
                ],
            }
        if "getpenaltydetails" in url_lower:
            if "7680361725085945110" in url:
                return {
                    "status_code": 0,
                    "appeal_status": 0,
                    "penalties": [
                        {
                            "date": "1788811033",
                            "issuer": "TNS",
                            "penalty_id": {"id": "7682884793714252566"},
                            "penalty_reason_info_list": [
                                {
                                    "code": "999",
                                    "title": "Community Guidelines",
                                    "content": "Ineligible for the For You feed (FYF) due to safety & community standards.",
                                    "link": "See Community Guidelines",
                                    "url": "https://www.tiktok.com/community-guidelines/overview/",
                                }
                            ],
                            "reason_codes": ["999"],
                        }
                    ],
                }
            return {
                "status_code": 0,
                "appeal_status": 2,
                "penalties": [],
            }
        return {"status_code": 0}

    with patch.object(service.client, "request_api", side_effect=mock_request_api):
        violations = service.fetch_video_violations(profile_id=78)

    assert len(violations) == 1
    v = violations[0]
    assert v["video_id"] == "7680361725085945110"
    assert v["title"] == "#fyp #shorts"
    assert "Community Guidelines" in v["violate_title"]
    assert "Ineligible for the For You feed" in v["violate_description"]
    assert v["status"] == "can_appeal"

    # Check persistence in violateVideos table
    conn = get_db_connection(test_db)
    rows = conn.execute("SELECT * FROM violateVideos WHERE profile_id=78").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0]["video_id"] == "7680361725085945110"


def test_passive_sync_deep_creator_api_insights_and_unmonetized_rpm(test_db: Path):
    """Verifies PassiveTikTokSyncService handles unmonetized status=2 correctly (RPM = 0.0, label='Chưa bật')."""
    from src.infrastructure.database.repositories.profile_repository import ProfileRepository
    from src.infrastructure.database.repositories.proxy_repository import ProxyRepository

    p_repo = ProfileRepository(db_path=test_db)
    px_repo = ProxyRepository(db_path=test_db)
    sync_service = PassiveTikTokSyncService(profile_repo=p_repo, proxy_repo=px_repo, db_path=test_db)

    def mock_request_api(profile_id, url, **kwargs):
        url_lower = url.lower()
        if "analytics/insights" in url_lower:
            return {
                "status_code": 0,
                "analytics_overview_rewards": {
                    "message": {"status": 2},
                    "total": {"message": {"status": 2}},
                },
                "analytics_overview_views": {
                    "delta_change": {"value": 112284},
                    "list": {
                        "value": [
                            {"value": 48913},
                            {"value": 50649},
                            {"value": 46094},
                            {"value": 44500},
                            {"value": 43352},
                            {"value": 47463},
                            {"value": 57389},
                        ]
                    },
                },
            }
        if "item_list/v1" in url_lower:
            return {
                "status_code": 0,
                "item_list": [
                    {
                        "item_id": "7680361725085945110",
                        "desc": "#fyp #shorts",
                        "play_count": 48913,
                        "like_count": 1890,
                        "comment_count": 21,
                        "share_count": 5,
                        "create_time": "1788800000",
                        "duration": 45,
                        "status": 102,
                    }
                ],
            }
        if "gethashcount" in url_lower:
            return {
                "status_code": 0,
                "item_count": 79,
                "total_item_count": 246,
                "like_count": 92267,
            }
        return {"status_code": 0}

    with patch.object(sync_service.client, "request_api", side_effect=mock_request_api):
        res = sync_service.sync_profile_deep_creator_api(profile_id=78)

    assert res is True
    row = p_repo.get_by_id(78)
    assert row["rpm"] == 0.0
    assert row["money_earned"] == 0.0
    assert row["views_month"] >= 48913
