"""
TDD Test Suite for Passive TikTok Data Collection & Telemetry Sniffing.
Learned from Gloglin2609 and SamMonny SDK:
1. DOM Hydration Extractor (__UNIVERSAL_DATA_FOR_REHYDRATION__ / SIGI_STATE).
2. Passive Network Sniffer (User detail, Creator revenue/RPM/Balance, Video items).
3. Offline SQLite Cookie Inspection (state_loggin_browser LIVE/DIE).
4. MetricsSyncWorker asynchronous dispatch without OAuth token requirements.
"""

import sqlite3
import time
from pathlib import Path

import pytest
from src.application.signals.app_signals import AppSignalBus
from src.application.workers.metrics_sync_worker import MetricsSyncWorker
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
from src.infrastructure.tiktok.dom_hydration_extractor import TikTokDomHydrationExtractor
from src.infrastructure.tiktok.network_sniffer import TikTokNetworkSniffer
from src.infrastructure.tiktok.passive_sync_service import PassiveTikTokSyncService


@pytest.fixture
def test_env(tmp_path: Path):
    db_file = tmp_path / "test_passive_app.db"
    run_all_migrations(db_file)
    profile_repo = ProfileRepository(db_file)
    proxy_repo = ProxyRepository(db_file)
    signal_bus = AppSignalBus.instance()
    extractor = TikTokDomHydrationExtractor()
    sniffer = TikTokNetworkSniffer(db_path=db_file, signal_bus=signal_bus)
    sync_service = PassiveTikTokSyncService(
        profile_repo=profile_repo,
        proxy_repo=proxy_repo,
        sniffer=sniffer,
        extractor=extractor,
        signal_bus=signal_bus,
    )
    return {
        "tmp_path": tmp_path,
        "db_file": db_file,
        "profile_repo": profile_repo,
        "proxy_repo": proxy_repo,
        "signal_bus": signal_bus,
        "extractor": extractor,
        "sniffer": sniffer,
        "sync_service": sync_service,
    }


def test_dom_hydration_extractor_parses_universal_data(test_env):
    extractor: TikTokDomHydrationExtractor = test_env["extractor"]

    sample_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">
        {
            "__DEFAULT_SCOPE__": {
                "webapp.user-detail": {
                    "userInfo": {
                        "user": {
                            "id": "718293849102",
                            "uniqueId": "viral_creator_99",
                            "nickname": "Viral Creator",
                            "avatarLarger": "https://p16.tiktokcdn.com/avatar1.jpg",
                            "signature": "Official TikTok MMO Creator #viral",
                            "region": "US",
                            "privateAccount": false
                        },
                        "stats": {
                            "followerCount": 125400,
                            "followingCount": 420,
                            "heartCount": 3890000,
                            "videoCount": 85
                        }
                    }
                }
            }
        }
        </script>
    </head>
    <body><div>Profile Page</div></body>
    </html>
    """

    res = extractor.extract(sample_html)
    assert res is not None
    assert res["uniqueId"] == "viral_creator_99"
    assert res["nickname"] == "Viral Creator"
    assert res["followerCount"] == 125400
    assert res["followingCount"] == 420
    assert res["heartCount"] == 3890000
    assert res["videoCount"] == 85
    assert res["avatarUrl"] == "https://p16.tiktokcdn.com/avatar1.jpg"
    assert "Official TikTok MMO" in res["signature"]
    assert res["region"] == "US"
    assert res["privacy"] == 0


def test_dom_hydration_extractor_parses_sigi_state_fallback(test_env):
    extractor: TikTokDomHydrationExtractor = test_env["extractor"]

    sigi_html = """
    <html>
    <body>
        <script id="SIGI_STATE" type="application/json">
        {
            "UserModule": {
                "users": {
                    "beta_account": {
                        "id": "992831",
                        "uniqueId": "beta_account",
                        "nickname": "Beta Channel",
                        "avatarMedium": "https://p16.tiktokcdn.com/avatar2.jpg",
                        "signature": "Beta bio description"
                    }
                },
                "stats": {
                    "beta_account": {
                        "followerCount": 54200,
                        "followingCount": 180,
                        "heart": 1200000,
                        "videoCount": 32
                    }
                }
            }
        }
        </script>
    </body>
    </html>
    """

    res = extractor.extract(sigi_html)
    assert res is not None
    assert res["uniqueId"] == "beta_account"
    assert res["followerCount"] == 54200
    assert res["videoCount"] == 32
    assert res["heartCount"] == 1200000


def test_network_sniffer_user_detail_payload(test_env):
    sniffer: TikTokNetworkSniffer = test_env["sniffer"]
    profile_repo: ProfileRepository = test_env["profile_repo"]

    p_id = profile_repo.create({"name": "ProfileSniffer1"})

    payload = {
        "userInfo": {
            "user": {
                "id": "88776655",
                "uniqueId": "mmo_master_us",
                "nickname": "MMO Master",
                "avatarLarger": "https://p16.tiktokcdn.com/avatar_large.jpg",
                "signature": "Building wealth with TikTok videos",
                "region": "US",
                "secUid": "MS4wLjABAAAAsecuid12345",
            },
            "stats": {
                "followerCount": 85000,
                "followingCount": 210,
                "heartCount": 1450000,
                "videoCount": 62,
            },
        }
    }

    handled = sniffer.process_api_response(
        profile_id=p_id,
        url="https://www.tiktok.com/api/user/detail/?aid=1988",
        data=payload,
    )
    assert handled is True

    updated_row = profile_repo.get_by_id(p_id)
    assert updated_row["username_on_tiktok"] == "mmo_master_us"
    assert updated_row["nickname"] == "MMO Master"
    assert updated_row["total_followers"] == 85000
    assert updated_row["total_following"] == 210
    assert updated_row["total_likes"] == 1450000
    assert updated_row["total_videos"] == 62
    assert updated_row["country"] == "US"
    assert updated_row["sec_uid"] == "MS4wLjABAAAAsecuid12345"


def test_network_sniffer_creator_dashboard_overview(test_env):
    sniffer: TikTokNetworkSniffer = test_env["sniffer"]
    profile_repo: ProfileRepository = test_env["profile_repo"]

    p_id = profile_repo.create({"name": "ProfileSniffer2"})

    dashboard_payload = {
        "overview": {
            "money_earned": 1425.80,
            "rpm": 0.95,
            "balance": 820.50,
            "qualified_views": 1500000,
            "currency": "USD",
            "state_kyc": "PASSED",
            "date_reapply": "2026-12-01",
        }
    }

    handled = sniffer.process_api_response(
        profile_id=p_id,
        url="https://www.tiktok.com/api/creator/dashboard/overview",
        data=dashboard_payload,
    )
    assert handled is True

    updated_row = profile_repo.get_by_id(p_id)
    assert updated_row["money_earned"] == 1425.80
    assert updated_row["rpm"] == 0.95
    assert updated_row["balance"] == 820.50
    assert updated_row["total_views"] == 1500000
    assert updated_row["currency"] == "USD"
    assert updated_row["state_kyc"] == "PASSED"
    assert updated_row["date_reapply"] == "2026-12-01"


def test_network_sniffer_post_item_list_populates_statistic_table(test_env):
    sniffer: TikTokNetworkSniffer = test_env["sniffer"]
    profile_repo: ProfileRepository = test_env["profile_repo"]
    db_file: Path = test_env["db_file"]

    p_id = profile_repo.create({"name": "ProfileItems"})

    post_list_payload = {
        "itemList": [
            {
                "id": "7199283746192837461",
                "desc": "Check out this crazy hack! #viral #fyp",
                "createTime": 1718000000,
                "stats": {
                    "playCount": 450000,
                    "diggCount": 38000,
                    "commentCount": 1200,
                    "shareCount": 5400,
                },
            },
            {
                "id": "7199283746192837462",
                "desc": "Part 2 of the secret strategy #mmo",
                "createTime": 1718100000,
                "stats": {
                    "playCount": 120000,
                    "diggCount": 8500,
                    "commentCount": 340,
                    "shareCount": 980,
                },
            },
        ]
    }

    handled = sniffer.process_api_response(
        profile_id=p_id,
        url="https://www.tiktok.com/api/post/item_list/?count=20",
        data=post_list_payload,
    )
    assert handled is True

    conn = sqlite3.connect(db_file)
    rows = conn.execute(
        "SELECT id_video, views, likes, comments, shares, title FROM statisticTable WHERE profile_id=?",
        (p_id,),
    ).fetchall()
    conn.close()

    assert len(rows) == 2
    vid_map = {r[0]: r for r in rows}
    assert "7199283746192837461" in vid_map
    assert vid_map["7199283746192837461"][1] == 450000  # views
    assert vid_map["7199283746192837461"][2] == 38000  # likes


def test_offline_cookie_extraction_updates_login_state(test_env):
    sync_service: PassiveTikTokSyncService = test_env["sync_service"]
    profile_repo: ProfileRepository = test_env["profile_repo"]
    tmp_path: Path = test_env["tmp_path"]

    # Create dummy profile dir with Network/Cookies SQLite DB
    prof_dir = tmp_path / "prof_cookie_test"
    net_dir = prof_dir / "Default" / "Network"
    net_dir.mkdir(parents=True, exist_ok=True)
    cookie_db = net_dir / "Cookies"

    # Create SQLite cookies table
    conn = sqlite3.connect(cookie_db)
    conn.execute(
        """
        CREATE TABLE cookies (
            creation_utc INTEGER NOT NULL,
            host_key TEXT NOT NULL,
            top_frame_site_key TEXT NOT NULL,
            name TEXT NOT NULL,
            value TEXT NOT NULL,
            encrypted_value BLOB NOT NULL,
            path TEXT NOT NULL,
            expires_utc INTEGER NOT NULL,
            is_secure INTEGER NOT NULL,
            is_httponly INTEGER NOT NULL,
            last_access_utc INTEGER NOT NULL,
            has_expires INTEGER NOT NULL,
            is_persistent INTEGER NOT NULL,
            priority INTEGER NOT NULL DEFAULT 1,
            samesite INTEGER NOT NULL DEFAULT -1,
            source_scheme INTEGER NOT NULL DEFAULT 2,
            source_port INTEGER NOT NULL DEFAULT 443,
            is_same_party INTEGER NOT NULL DEFAULT 0,
            last_update_utc INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (host_key, top_frame_site_key, name, path)
        );
        """
    )
    # Insert sessionid cookie with future expiration
    future_ldap = int((time.time() + 86400 * 30 + 11644473600) * 1000000)
    conn.execute(
        """
        INSERT INTO cookies (creation_utc, host_key, top_frame_site_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly, last_access_utc, has_expires, is_persistent)
        VALUES (?, '.tiktok.com', '', 'sessionid', 'abc123sessiontoken', X'', '/', ?, 1, 1, ?, 1, 1);
        """,
        (future_ldap, future_ldap, future_ldap),
    )
    conn.execute(
        """
        INSERT INTO cookies (creation_utc, host_key, top_frame_site_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly, last_access_utc, has_expires, is_persistent)
        VALUES (?, '.tiktok.com', '', 'ttwid', 'ttwid_sample_value', X'', '/', ?, 1, 1, ?, 1, 1);
        """,
        (future_ldap, future_ldap, future_ldap),
    )
    conn.commit()
    conn.close()

    p_id = profile_repo.create({"name": "CookieLiveProfile", "storage_dir": str(prof_dir)})

    # Run passive sync on this profile
    res = sync_service.sync_profile_offline_cookies(p_id)
    assert res["is_live"] is True
    assert "sessionid" in res["cookies"]

    row = profile_repo.get_by_id(p_id)
    assert row["state_loggin_browser"] == 1
    assert row["status"] == "LIVE"
    assert "abc123sessiontoken" in (row.get("cookies_json") or "")


def test_metrics_sync_worker_triggers_passive_service(test_env, monkeypatch):
    sync_service: PassiveTikTokSyncService = test_env["sync_service"]
    profile_repo: ProfileRepository = test_env["profile_repo"]
    signal_bus: AppSignalBus = test_env["signal_bus"]

    p_id = profile_repo.create({"name": "WorkerTestProfile", "username_on_tiktok": "test_user"})

    # Track emitted signals
    emitted_profiles = []
    signal_bus.profile_updated.connect(lambda pid, d: emitted_profiles.append((pid, d)))

    # Dummy implementation of sync_single_profile
    def mock_sync(pid: int) -> dict:
        return {"status": "LIVE", "total_followers": 9999}

    monkeypatch.setattr(sync_service, "sync_single_profile", mock_sync)

    from src.application.services.profile_service import ProfileService

    mock_prof_service = ProfileService(profile_repo=profile_repo, sync_service=sync_service)

    worker = MetricsSyncWorker(
        profile_ids=[p_id],
        profile_service=mock_prof_service,
        signal_bus=signal_bus,
    )
    worker.execute()

    assert len(emitted_profiles) == 1
    assert emitted_profiles[0][0] == p_id
    assert emitted_profiles[0][1]["total_followers"] == 9999
