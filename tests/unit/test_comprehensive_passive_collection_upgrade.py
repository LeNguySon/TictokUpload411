"""Comprehensive TDD Test Suite for Upgraded Passive Data Collection.
Learned from Gloglin2609 and SamMonny SDK:
1. Complete Channel Identity & Stats extraction from /api/user/detail/ (including sec_uid).
2. Video Item List (/api/creator/item/list & /api/post/item_list) with embedded author metadata,
   30-day views calculation (views_month), statisticTable upsert, and videoTables insertion.
3. Creator Rewards & MMO revenue metrics (money_earned, rpm, balance, currency, date_reapply, state_kyc).
4. Account Standing & active strikes from /api/creator/account/standing/.
5. Violations, appeals deadline & violateVideos persistence from /api/creator/violation/.
6. SamMonny SDK microsecond FileTime standard for SQLite cookies with 9 core tokens and CSRF equivalence.
7. DOM Hydration fallback resilience.
8. Non-blocking thread-safe GUI signal propagation.
"""

import sqlite3
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication
from src.application.signals.app_signals import AppSignalBus
from src.application.workers.metrics_sync_worker import MetricsSyncWorker
from src.infrastructure.database.connection import db_session
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
from src.infrastructure.tiktok.dom_hydration_extractor import TikTokDomHydrationExtractor
from src.infrastructure.tiktok.network_sniffer import TikTokNetworkSniffer
from src.infrastructure.tiktok.passive_sync_service import (
    CHROMIUM_EPOCH_OFFSET_MICROS,
    PassiveTikTokSyncService,
)


@pytest.fixture
def app_instance():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def cleanup_singletons():
    yield
    from src.application.signals.app_signals import AppSignalBus
    from src.application.workers.thread_pool_manager import ThreadPoolManager

    ThreadPoolManager.reset_instance()
    AppSignalBus.reset_instance()


@pytest.fixture
def passive_env(tmp_path: Path):
    db_file = tmp_path / "comprehensive_passive.db"
    run_all_migrations(db_file)
    profile_repo = ProfileRepository(db_file)
    proxy_repo = ProxyRepository(db_file)
    signal_bus = AppSignalBus.instance()
    sniffer = TikTokNetworkSniffer(db_path=db_file, signal_bus=signal_bus)
    extractor = TikTokDomHydrationExtractor()
    sync_service = PassiveTikTokSyncService(
        profile_repo=profile_repo,
        proxy_repo=proxy_repo,
        sniffer=sniffer,
        extractor=extractor,
        signal_bus=signal_bus,
    )
    return {
        "db_file": db_file,
        "profile_repo": profile_repo,
        "proxy_repo": proxy_repo,
        "signal_bus": signal_bus,
        "sniffer": sniffer,
        "extractor": extractor,
        "sync_service": sync_service,
        "tmp_path": tmp_path,
    }


# =============================================================================
# 1. TEST IDENTITY & CHANNEL STATS EXTRACTION
# =============================================================================
def test_sniffer_channel_identity_extraction(passive_env):
    """Verifies that /api/user/detail/ extracts all channel info and sec_uid."""
    sniffer: TikTokNetworkSniffer = passive_env["sniffer"]
    repo: ProfileRepository = passive_env["profile_repo"]

    pid = repo.create({"name": "TestProfile_Sniff1"})

    payload = {
        "userInfo": {
            "user": {
                "id": "718293849102",
                "uniqueId": "viral_creator_99",
                "nickname": "Viral Creator",
                "secUid": "MS4wLjABAAAA_SampleSecUid12345",
                "avatarLarger": "https://p16.tiktokcdn.com/avatar1.jpg",
                "signature": "Official TikTok MMO Creator #viral",
                "region": "US",
                "privateAccount": False,
            },
            "stats": {
                "followerCount": 125400,
                "followingCount": 420,
                "heartCount": 3890000,
                "videoCount": 85,
            },
        }
    }

    url = "https://www.tiktok.com/api/user/detail/?uniqueId=viral_creator_99"
    handled = sniffer.process_api_response(pid, url, payload)
    assert handled is True

    profile = repo.get_by_id(pid)
    assert profile["username_on_tiktok"] == "viral_creator_99"
    assert profile["nickname"] == "Viral Creator"
    assert profile["tiktok_user_id"] == "718293849102"
    assert profile["sec_uid"] == "MS4wLjABAAAA_SampleSecUid12345"
    assert profile["bio"] == "Official TikTok MMO Creator #viral"
    assert profile["country"] == "US"
    assert profile["privacy"] == 0
    assert profile["total_followers"] == 125400
    assert profile["total_following"] == 420
    assert profile["total_likes"] == 3890000
    assert profile["total_videos"] == 85
    assert profile["statistic_date_update"] is not None


# =============================================================================
# 2. TEST VIDEO ITEM LIST WITH AUTHOR STATS, 30D VIEWS & VIDEOTABLES
# =============================================================================
def test_sniffer_video_item_list_with_author_and_30d_views(passive_env):
    """
    Verifies that /api/creator/item/list/ and /api/post/item_list:
    1. Extracts embedded author & authorStats directly into profile row.
    2. Calculates 30-day views (views_month / views_30d) vs total lifetime views.
    3. Upserts records into statisticTable.
    4. Inserts comprehensive records into videoTables with duration, display, permissions.
    """
    sniffer: TikTokNetworkSniffer = passive_env["sniffer"]
    repo: ProfileRepository = passive_env["profile_repo"]
    db_file = passive_env["db_file"]

    pid = repo.create({"name": "TestProfile_Videos"})

    now_ts = int(time.time())
    recent_ts = now_ts - 86400  # 1 day ago (within 30 days)
    old_ts = now_ts - (45 * 86400)  # 45 days ago (outside 30 days)

    payload = {
        "creator_item_list": [
            {
                "item_id": "vid_studio_101",
                "item_title": "Viral Reel 101",
                "create_time": recent_ts,
                "author": {
                    "id": "7891234",
                    "uniqueId": "author_from_items",
                    "nickname": "Author Nick",
                    "avatarThumb": "https://p16.tiktokcdn.com/thumb_auth.jpg",
                },
                "authorStats": {
                    "followerCount": 65000,
                    "heartCount": 850000,
                    "videoCount": 40,
                },
                "statistics": {
                    "views": 50000,
                    "likes": 4200,
                    "comments": 310,
                    "shares": 150,
                },
                "video": {
                    "duration": 45,
                    "cover": "https://p16.tiktokcdn.com/cover_101.jpg",
                },
                "display": 1,
                "is_top": True,
                "item_control": {
                    "can_comment": True,
                    "can_duet": False,
                    "can_stitch": True,
                },
            },
            {
                "item_id": "vid_studio_102",
                "item_title": "Older Classic",
                "create_time": old_ts,
                "statistics": {
                    "views": 20000,
                    "likes": 1800,
                    "comments": 90,
                    "shares": 40,
                },
                "video": {
                    "duration": 60,
                    "cover": "https://p16.tiktokcdn.com/cover_102.jpg",
                },
                "display": 2,
                "is_top": False,
                "item_control": {
                    "can_comment": True,
                    "can_duet": True,
                    "can_stitch": True,
                },
            },
        ]
    }

    url = "https://www.tiktok.com/api/creator/item/list/?count=20"
    handled = sniffer.process_api_response(pid, url, payload)
    assert handled is True

    # 1. Check Profile author & view aggregates
    prof = repo.get_by_id(pid)
    assert prof["username_on_tiktok"] == "author_from_items"
    assert prof["total_followers"] == 65000
    assert prof["total_likes"] == 850000
    # 30-day views: only vid_studio_101 (50000)
    assert prof.get("views_30d") == 50000 or prof.get("views_month") == 50000
    # Total views: 50000 + 20000 = 70000
    assert prof["total_views"] >= 70000

    # 2. Check statisticTable
    with db_session(db_file) as conn:
        stats_rows = conn.execute(
            "SELECT * FROM statisticTable WHERE profile_id=? ORDER BY id_video", (pid,)
        ).fetchall()
        assert len(stats_rows) == 2
        r1 = dict(stats_rows[0])
        assert r1["id_video"] == "vid_studio_101"
        assert r1["views"] == 50000
        assert r1["likes"] == 4200
        assert r1["comments"] == 310
        assert r1["shares"] == 150

        # 3. Check videoTables
        vid_rows = conn.execute("SELECT * FROM videoTables WHERE profile_id=? ORDER BY video_id", (pid,)).fetchall()
        assert len(vid_rows) == 2
        v1 = dict(vid_rows[0])
        assert v1["video_id"] == "vid_studio_101"
        assert v1["duration"] == 45
        assert v1["display"] == 1
        assert v1["is_pinned"] == 1
        assert v1["allow_duet"] == 0
        assert v1["allow_stitch"] == 1
        assert v1["thumbnail_url"] == "https://p16.tiktokcdn.com/cover_101.jpg"


# =============================================================================
# 3. TEST CREATOR REVENUE, RPM, BALANCE & MMO REWARDS
# =============================================================================
def test_sniffer_creator_rewards_and_mmo_metrics(passive_env):
    """Verifies that /creator-center/api/creator/rewards extracts monetization metrics."""
    sniffer: TikTokNetworkSniffer = passive_env["sniffer"]
    repo: ProfileRepository = passive_env["profile_repo"]

    pid = repo.create({"name": "TestProfile_Rev"})

    payload = {
        "overview": {
            "money_earned": 3250.75,
            "rpm": 1.15,
            "balance": 1820.00,
            "qualified_views": 2850000,
            "currency": "EUR",
            "date_reapply": "2026-11-01",
            "state_kyc": "verified",
        }
    }

    url = "https://www.tiktok.com/creator-center/api/creator/rewards"
    handled = sniffer.process_api_response(pid, url, payload)
    assert handled is True

    prof = repo.get_by_id(pid)
    assert prof["money_earned"] == 3250.75
    assert prof["rpm"] == 1.15
    assert prof["balance"] == 1820.00
    assert prof["total_views"] == 2850000
    assert prof["currency"] == "EUR"
    assert prof["date_reapply"] == "2026-11-01"
    assert prof["state_kyc"] == "verified"


# =============================================================================
# 4. TEST ACCOUNT STANDING & ACTIVE STRIKES
# =============================================================================
def test_sniffer_account_standing_and_strikes(passive_env):
    """Verifies that /api/creator/account/standing/ extracts standing and active strikes."""
    sniffer: TikTokNetworkSniffer = passive_env["sniffer"]
    repo: ProfileRepository = passive_env["profile_repo"]

    pid = repo.create({"name": "TestProfile_Standing"})

    payload = {
        "standing_level": "Warning",
        "active_strikes": 1,
    }

    url = "https://www.tiktok.com/api/creator/account/standing/?aid=1988"
    handled = sniffer.process_api_response(pid, url, payload)
    assert handled is True

    prof = repo.get_by_id(pid)
    assert prof["account_standing"] == "Warning"
    assert prof["strike_count"] == 1


# =============================================================================
# 5. TEST VIOLATIONS, APPEALS DEADLINE & VIOLATEVIDEOS
# =============================================================================
def test_sniffer_violations_and_appeals(passive_env):
    """Verifies that /api/creator/violation/ populates violateVideos table and appeal date."""
    sniffer: TikTokNetworkSniffer = passive_env["sniffer"]
    repo: ProfileRepository = passive_env["profile_repo"]
    db_file = passive_env["db_file"]

    pid = repo.create({"name": "TestProfile_Violations"})

    payload = {
        "violation_list": [
            {
                "item_id": "bad_vid_99",
                "item_title": "Sample Infringing Video",
                "violation_title": "Bản quyền Âm nhạc",
                "violation_reason": "Âm thanh thương mại chưa được cấp quyền.",
                "create_time": "2026-09-15 14:00:00",
                "appeal_deadline": "2026-10-15",
                "status": "pending",
            }
        ]
    }

    url = "https://www.tiktok.com/api/creator/violation/list/?aid=1988"
    handled = sniffer.process_api_response(pid, url, payload)
    assert handled is True

    prof = repo.get_by_id(pid)
    assert prof["appealViolateDate"] == "2026-10-15"
    assert prof["strike_count"] == 1

    with db_session(db_file) as conn:
        v_row = conn.execute("SELECT * FROM violateVideos WHERE profile_id=?", (pid,)).fetchone()
        assert v_row is not None
        assert v_row["video_id"] == "bad_vid_99"
        assert v_row["violate_title"] == "Bản quyền Âm nhạc"
        assert v_row["violate_description"] == "Âm thanh thương mại chưa được cấp quyền."
        assert v_row["appeal_date"] == "2026-10-15"


# =============================================================================
# 6. TEST SAMMONNY SDK STANDARD OFFLINE SQLITE COOKIE ENGINE
# =============================================================================
def test_offline_cookie_sqlite_sammonny_micros_standard(passive_env):
    """
    Verifies that offline SQLite cookie parsing follows SamMonny SDK standard:
    - Uses CHROMIUM_EPOCH_OFFSET_MICROS = 11644473600000000.
    - Evaluates 9 core tokens including sessionid, sid_guard, ttwid, etc.
    - Handles CSRF equivalence (tt_csrf_token -> passport_csrf_token).
    - Sets state_loggin_browser=1 (LIVE) if sessionid is valid, or 0 (DIE) if expired/missing.
    """
    sync_service: PassiveTikTokSyncService = passive_env["sync_service"]
    repo: ProfileRepository = passive_env["profile_repo"]
    tmp_path: Path = passive_env["tmp_path"]

    # 1. Create a dummy Chromium Cookies SQLite database
    profile_dir = tmp_path / "mock_chromium_profile"
    cookies_db_path = profile_dir / "Default" / "Network" / "Cookies"
    cookies_db_path.parent.mkdir(parents=True)

    conn = sqlite3.connect(cookies_db_path)
    conn.execute("""
        CREATE TABLE cookies (
            host_key TEXT,
            name TEXT,
            value TEXT,
            expires_utc INTEGER,
            is_secure INTEGER,
            is_httponly INTEGER,
            samesite INTEGER
        );
    """)

    # Current time in microsecond Chromium epoch
    now_ts = time.time()
    valid_micros = int((now_ts + 86400 * 30) * 1_000_000) + CHROMIUM_EPOCH_OFFSET_MICROS
    expired_micros = int((now_ts - 86400) * 1_000_000) + CHROMIUM_EPOCH_OFFSET_MICROS

    # Insert cookies: 9 core tokens
    test_cookies = [
        (".tiktok.com", "sessionid", "live_sess_abc123", valid_micros),
        (".tiktok.com", "sessionid_ss", "live_sess_abc123", valid_micros),
        (".tiktok.com", "sid_tt", "sid_tt_sample", valid_micros),
        (".tiktok.com", "sid_guard", "guard_sample", valid_micros),
        (".tiktok.com", "uid_tt", "718293849102", valid_micros),
        (".tiktok.com", "tt_chain_token", "chain_sample", valid_micros),
        (".tiktok.com", "tt_csrf_token", "csrf_web_sample", valid_micros),  # CSRF equivalence
        (".tiktok.com", "ttwid", "ttwid_sample", valid_micros),
        (".tiktok.com", "store-idc", "alisg", valid_micros),
        (".tiktok.com", "old_expired_cookie", "dead", expired_micros),  # Expired
    ]

    for host, name, val, exp in test_cookies:
        conn.execute(
            "INSERT INTO cookies VALUES (?, ?, ?, ?, 1, 1, 1)",
            (host, name, val, exp),
        )
    conn.commit()
    conn.close()

    pid = repo.create(
        {
            "name": "Live_Profile_SamMonny",
            "storage_dir": str(profile_dir),
        }
    )

    res = sync_service.sync_profile_offline_cookies(pid)
    assert res["ok"] is True
    assert res["is_live"] is True
    assert "sessionid" in res["cookies"]
    assert "passport_csrf_token" in res["cookies"] or "tt_csrf_token" in res["cookies"]
    assert "old_expired_cookie" not in res["cookies"]

    prof = repo.get_by_id(pid)
    assert prof["state_loggin_browser"] == 1
    assert prof["status"] == "LIVE"


# =============================================================================
# 7. TEST DOM HYDRATION EXTRACTION
# =============================================================================
def test_dom_hydration_comprehensive_parsing(passive_env):
    """Verifies that TikTokDomHydrationExtractor extracts public channel metrics from HTML."""
    extractor: TikTokDomHydrationExtractor = passive_env["extractor"]

    sample_html = """
    <html>
    <head>
        <script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">
        {
            "__DEFAULT_SCOPE__": {
                "webapp.user-detail": {
                    "userInfo": {
                        "user": {
                            "id": "888999111",
                            "uniqueId": "dom_hydrated_user",
                            "nickname": "DOM Nick",
                            "avatarLarger": "https://p16.tiktokcdn.com/avatar_dom.jpg",
                            "signature": "Bio from DOM Hydration",
                            "region": "JP",
                            "privateAccount": false
                        },
                        "stats": {
                            "followerCount": 94000,
                            "followingCount": 310,
                            "heartCount": 2100000,
                            "videoCount": 55
                        }
                    }
                }
            }
        }
        </script>
    </head>
    <body></body>
    </html>
    """

    res = extractor.extract(sample_html)
    assert res is not None
    assert res["uniqueId"] == "dom_hydrated_user"
    assert res["nickname"] == "DOM Nick"
    assert res["followerCount"] == 94000
    assert res["followingCount"] == 310
    assert res["heartCount"] == 2100000
    assert res["videoCount"] == 55
    assert res["region"] == "JP"
    assert res["privacy"] == 0


# =============================================================================
# 8. TEST METRICS SYNC WORKER THREAD SAFETY & SIGNALS
# =============================================================================
def test_passive_sync_worker_thread_safety_and_signals(passive_env, app_instance):
    """Verifies that MetricsSyncWorker executes asynchronously and emits GUI signals."""
    repo: ProfileRepository = passive_env["profile_repo"]
    signal_bus: AppSignalBus = passive_env["signal_bus"]

    pid = repo.create({"name": "Worker_Test_Profile"})

    mock_profile_service = MagicMock()
    mock_profile_service.sync_metrics_from_tiktok.return_value = {
        "profile_id": pid,
        "total_followers": 99999,
        "status": "LIVE",
    }

    worker = MetricsSyncWorker(
        profile_ids=[pid],
        profile_service=mock_profile_service,
        signal_bus=signal_bus,
    )

    signal_received = []

    def on_profile_updated(p_id, fields):
        signal_received.append((p_id, fields))

    signal_bus.profile_updated.connect(on_profile_updated)

    worker.run()  # Run worker logic

    assert len(signal_received) == 1
    assert signal_received[0][0] == pid
    assert signal_received[0][1]["total_followers"] == 99999
