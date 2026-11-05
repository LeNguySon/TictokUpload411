"""
TDD Unit Test Suite for Deep Data Collection Suite (Telemetry 4-Tier Engine).
Conforms strictly to ECC Development Lifecycle (Tier 4 Large).
Tests:
1. Full Deep Sync executes Creator APIs and updates profiles, statisticTable, videoTables, violateVideos.
2. Accurate calculation of 30-day views (views_month) vs total_views across video items.
3. Clean fallback to DOM hydration when no cookies are available.
4. Resilient error handling when individual Creator endpoints fail.
"""

import time
from pathlib import Path
from unittest.mock import patch

import pytest
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
from src.infrastructure.tiktok.passive_sync_service import PassiveTikTokSyncService


@pytest.fixture
def isolated_db_env(tmp_path: Path):
    db_file = tmp_path / "deep_telemetry_test.db"
    run_all_migrations(db_file)
    prof_repo = ProfileRepository(db_file)
    proxy_repo = ProxyRepository(db_file)
    px_id = proxy_repo.create(
        host="1.2.3.4",
        port=8080,
        username="user",
        password="pwd",
        protocol="http",
    )
    p_id = prof_repo.create(
        name="telemetry_channel",
        project_id=1,
        proxy_id=px_id,
        cookies_json='[{"name": "sessionid", "value": "test_session_123"}]',
    )
    return {
        "db_file": db_file,
        "prof_repo": prof_repo,
        "proxy_repo": proxy_repo,
        "profile_id": p_id,
        "proxy_id": px_id,
    }


def test_deep_sync_executes_creator_api_and_updates_all_tables(isolated_db_env):
    """Verifies that Deep Sync orchestrates Creator Center APIs and updates all 4 tables."""
    db_file = isolated_db_env["db_file"]
    prof_repo: ProfileRepository = isolated_db_env["prof_repo"]
    proxy_repo: ProxyRepository = isolated_db_env["proxy_repo"]
    pid = isolated_db_env["profile_id"]

    service = PassiveTikTokSyncService(
        profile_repo=prof_repo,
        proxy_repo=proxy_repo,
        db_path=db_file,
    )

    now_ts = int(time.time())

    # Simulated API payloads
    user_detail_payload = {
        "userInfo": {
            "user": {
                "id": "777888999",
                "uniqueId": "telemetry_channel",
                "nickname": "Telemetry Pro MMO",
                "secUid": "sec_uid_abc_123",
                "avatarThumb": "https://p16-sign.tiktokcdn.com/avatar.jpg",
                "signature": "Official MMO Channel 2026",
            },
            "stats": {
                "followerCount": 125000,
                "followingCount": 42,
                "heartCount": 980000,
                "videoCount": 25,
            },
        }
    }

    item_list_payload = {
        "itemList": [
            {
                "id": "vid_101",
                "desc": "Viral Video 1 #foryou",
                "createTime": now_ts - 86400 * 2,  # 2 days ago
                "stats": {
                    "playCount": 50000,
                    "diggCount": 3500,
                    "commentCount": 210,
                    "shareCount": 95,
                },
            },
            {
                "id": "vid_102",
                "desc": "Viral Video 2 #mmo",
                "createTime": now_ts - 86400 * 10,  # 10 days ago
                "stats": {
                    "playCount": 25000,
                    "diggCount": 1800,
                    "commentCount": 90,
                    "shareCount": 40,
                },
            },
        ]
    }

    overview_payload = {
        "overview": {
            "money_earned": 345.67,
            "rpm": 1.25,
            "balance": 890.12,
            "state_kyc": "PASSED",
            "date_reapply": "2026-12-01",
        }
    }

    violation_payload = {
        "violations": [
            {
                "id": "vid_bad_99",
                "title": "Violating Clip",
                "violation_title": "Unoriginal Content",
                "violation_reason": "Low creative effort detected",
                "appeal_deadline": "2026-11-20",
                "status": "warning",
            }
        ]
    }

    def mock_request_api(profile_id, url, **kwargs):
        if "/api/user/detail" in url:
            return user_detail_payload
        elif "/item/list" in url:
            return item_list_payload
        elif "/overview" in url or "/rewards" in url or "/income" in url:
            return overview_payload
        elif "/violation" in url:
            return violation_payload
        return {}

    with patch.object(service.client, "request_api", side_effect=mock_request_api):
        with patch("src.infrastructure.tiktok.passive_sync_service.download_and_cache_avatar"):
            res = service.sync_single_profile(pid)

            assert res.get("profile_id") == pid
            assert res.get("deep_synced") is True

    # 1. Verify profiles table
    row = prof_repo.get_by_id(pid)
    assert row["total_followers"] == 125000
    assert row["total_likes"] == 980000
    assert row["total_videos"] == 25
    assert row["nickname"] == "Telemetry Pro MMO"
    assert row["sec_uid"] == "sec_uid_abc_123"
    assert row["money_earned"] == 345.67
    assert row["rpm"] == 1.25
    assert row["balance"] == 890.12
    assert row["state_kyc"] == "PASSED"
    assert row["views_month"] == 75000  # 50k + 25k (both within 30 days)
    assert row["total_views"] == 75000

    # 2. Verify statisticTable & videoTables
    from src.infrastructure.database.connection import db_session
    with db_session(db_file, write=False) as conn:
        stats_rows = conn.execute("SELECT * FROM statisticTable WHERE profile_id = ?", (pid,)).fetchall()
        assert len(stats_rows) == 2
        vid_rows = conn.execute("SELECT * FROM videoTables WHERE profile_id = ?", (pid,)).fetchall()
        assert len(vid_rows) == 2

        # 3. Verify violateVideos
        viol_rows = conn.execute("SELECT * FROM violateVideos WHERE profile_id = ?", (pid,)).fetchall()
        assert len(viol_rows) == 1
        assert viol_rows[0]["video_id"] == "vid_bad_99"
        assert viol_rows[0]["violate_title"] == "Unoriginal Content"


def test_deep_sync_calculates_views_month_accurately(isolated_db_env):
    """Verifies that views_month separates 30-day view counts from lifetime total_views."""
    db_file = isolated_db_env["db_file"]
    prof_repo: ProfileRepository = isolated_db_env["prof_repo"]
    proxy_repo: ProxyRepository = isolated_db_env["proxy_repo"]
    pid = isolated_db_env["profile_id"]

    service = PassiveTikTokSyncService(
        profile_repo=prof_repo,
        proxy_repo=proxy_repo,
        db_path=db_file,
    )

    now_ts = int(time.time())

    # Video 1: 5 days ago (within 30d) -> 10,000 views
    # Video 2: 25 days ago (within 30d) -> 5,000 views
    # Video 3: 40 days ago (older than 30d) -> 50,000 views
    item_list_payload = {
        "itemList": [
            {
                "id": "v1",
                "desc": "Recent 1",
                "createTime": now_ts - 86400 * 5,
                "stats": {"playCount": 10000},
            },
            {
                "id": "v2",
                "desc": "Recent 2",
                "createTime": now_ts - 86400 * 25,
                "stats": {"playCount": 5000},
            },
            {
                "id": "v3",
                "desc": "Old 3",
                "createTime": now_ts - 86400 * 40,
                "stats": {"playCount": 50000},
            },
        ]
    }

    def mock_request(profile_id, url, **kwargs):
        if "/item/list" in url:
            return item_list_payload
        return {}

    with patch.object(service.client, "request_api", side_effect=mock_request):
        with patch("src.infrastructure.tiktok.passive_sync_service.download_and_cache_avatar"):
            service.sync_single_profile(pid)

    row = prof_repo.get_by_id(pid)
    # views_month must only count v1 + v2 = 15,000
    assert row["views_month"] == 15000
    # total_views must count all 3 = 65,000
    assert row["total_views"] == 65000


def test_deep_sync_falls_back_to_dom_hydration_when_no_cookies(isolated_db_env):
    """Verifies that profiles without cookies fall back to DOM hydration gracefully."""
    prof_repo: ProfileRepository = isolated_db_env["prof_repo"]
    proxy_repo: ProxyRepository = isolated_db_env["proxy_repo"]
    px_id = isolated_db_env["proxy_id"]

    # Profile without cookies
    p_no_cookie = prof_repo.create(
        name="no_cookie_user",
        project_id=1,
        proxy_id=px_id,
        cookies_json=None,
        cookies_browser=None,
    )

    service = PassiveTikTokSyncService(
        profile_repo=prof_repo,
        proxy_repo=proxy_repo,
        db_path=isolated_db_env["db_file"],
    )

    mock_hydration = {
        "followerCount": 5400,
        "followingCount": 120,
        "heartCount": 89000,
        "videoCount": 14,
        "nickname": "Public No Cookie",
    }

    with patch.object(service, "sync_profile_dom_hydration", return_value=mock_hydration) as mock_dom:
        res = service.sync_single_profile(p_no_cookie)

        assert res.get("profile_id") == p_no_cookie
        mock_dom.assert_called_once_with(p_no_cookie)


def test_deep_sync_tolerates_partial_api_failure(isolated_db_env):
    """Verifies that failures on individual endpoints do not disrupt overall synchronization."""
    db_file = isolated_db_env["db_file"]
    prof_repo: ProfileRepository = isolated_db_env["prof_repo"]
    proxy_repo: ProxyRepository = isolated_db_env["proxy_repo"]
    pid = isolated_db_env["profile_id"]

    service = PassiveTikTokSyncService(
        profile_repo=prof_repo,
        proxy_repo=proxy_repo,
        db_path=db_file,
    )

    def mock_flaky_request(profile_id, url, **kwargs):
        if "/api/user/detail" in url:
            return {
                "userInfo": {
                    "user": {"uniqueId": "flaky_user", "nickname": "Flaky Channel"},
                    "stats": {"followerCount": 1000},
                }
            }
        elif "/overview" in url:
            raise RuntimeError("Cloudflare 403 or network timeout")
        elif "/violation" in url:
            return {"status_code": 500, "error": "Internal Error"}
        return {}

    with patch.object(service.client, "request_api", side_effect=mock_flaky_request):
        with patch("src.infrastructure.tiktok.passive_sync_service.download_and_cache_avatar"):
            res = service.sync_single_profile(pid)
            assert res.get("profile_id") == pid

    row = prof_repo.get_by_id(pid)
    # The user detail that succeeded must be preserved
    assert row["total_followers"] == 1000
    assert row["nickname"] == "Flaky Channel"
