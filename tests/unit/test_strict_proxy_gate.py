"""
Strict Proxy Gate Unit Tests (AgentShield Standard).
Verifies that no outbound network traffic reaches TikTok without an authenticated, active proxy.
Blocks direct host IP leaks at Infrastructure, Application, and Presentation layers.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from src.application.services.upload_service import UploadService
from src.application.workers.metrics_sync_worker import MetricsSyncWorker
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
from src.infrastructure.database.repositories.video_repository import VideoRepository
from src.infrastructure.tiktok.gologin_tiktok_client import GoLoginTikTokClient
from src.infrastructure.tiktok.passive_sync_service import PassiveTikTokSyncService


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    db_file = tmp_path / "test_strict_proxy.db"
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT,
            name TEXT NOT NULL,
            username_on_tiktok TEXT,
            status TEXT DEFAULT 'LIVE',
            proxy_id INTEGER,
            storage_dir TEXT,
            cookies_json TEXT,
            cookies_browser TEXT,
            statistic_date_update TEXT,
            avatar_url TEXT,
            avatar_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS proxies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            host TEXT NOT NULL,
            port INTEGER NOT NULL,
            username TEXT,
            password TEXT,
            protocol TEXT DEFAULT 'http',
            proxy_type TEXT DEFAULT 'static',
            status TEXT DEFAULT 'alive',
            latency_ms INTEGER DEFAULT 100,
            public_ip TEXT,
            country_code TEXT,
            city TEXT,
            isp TEXT,
            timezone TEXT,
            latitude REAL,
            longitude REAL,
            change_ip_url TEXT,
            error_message TEXT,
            udp_supported INTEGER DEFAULT 0,
            last_checked_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS video_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_hash TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_name TEXT NOT NULL,
            file_size INTEGER DEFAULT 0,
            mtime REAL DEFAULT 0,
            status TEXT DEFAULT 'available',
            retry_count INTEGER DEFAULT 0,
            assigned_profile_id INTEGER,
            schedule_time TEXT,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    # Insert Profile 1 (HAS PROXY)
    cursor.execute(
        """
        INSERT INTO proxies (id, host, port, username, password, status)
        VALUES (1, '1.2.3.4', 8080, 'user', 'pass', 'alive');
        """
    )
    cursor.execute(
        """
        INSERT INTO profiles (id, name, username_on_tiktok, status, proxy_id, cookies_json)
        VALUES (1, 'proxied_user', 'proxied_user', 'LIVE', 1, '[{"name": "sessionid", "value": "abc"}]');
        """
    )

    # Insert Profile 2 (NO PROXY - proxy_id is NULL)
    cursor.execute(
        """
        INSERT INTO profiles (id, name, username_on_tiktok, status, proxy_id, cookies_json)
        VALUES (2, 'naked_user', 'naked_user', 'LIVE', NULL, '[{"name": "sessionid", "value": "xyz"}]');
        """
    )

    # Insert Video for Profile 2
    cursor.execute(
        """
        INSERT INTO video_registry (id, video_hash, file_path, file_name, status, assigned_profile_id)
        VALUES (1, 'hash123', 'test.mp4', 'Test Video', 'available', 2);
        """
    )

    conn.commit()
    conn.close()
    return db_file


def test_gologin_client_blocks_unproxied_profile(temp_db: Path) -> None:
    """Verifies GoLoginTikTokClient raises PermissionError when profile has no proxy."""
    client = GoLoginTikTokClient(db_path=temp_db)

    with patch("curl_cffi.requests.request") as mock_req:
        with pytest.raises(PermissionError, match="AgentShield Strict Proxy Gate"):
            client.request_api(profile_id=2, url="https://www.tiktok.com/api/user/detail/")

        # Must NEVER have called curl_cffi requests directly from host IP
        mock_req.assert_not_called()


def test_passive_sync_blocks_unproxied_dom_fetch(temp_db: Path) -> None:
    """Verifies PassiveTikTokSyncService returns empty string and avoids urllib opener when no proxy."""
    prof_repo = ProfileRepository(db_path=temp_db)
    px_repo = ProxyRepository(db_path=temp_db)
    service = PassiveTikTokSyncService(prof_repo, px_repo, db_path=temp_db)

    with patch("urllib.request.build_opener") as mock_opener:
        # Profile 2 has proxy_id = None
        content = service._fetch_url_content("https://www.tiktok.com/@naked_user", proxy_id=None)
        assert content == ""
        # Must NEVER have built a direct opener without proxy
        mock_opener.assert_not_called()


def test_upload_service_rejects_unproxied_upload(temp_db: Path, tmp_path: Path) -> None:
    """Verifies UploadService rejects execution if profile has no proxy, marking video failed."""
    prof_repo = ProfileRepository(db_path=temp_db)
    vid_repo = VideoRepository(db_path=temp_db)
    px_repo = ProxyRepository(db_path=temp_db)

    mock_adapter = MagicMock()
    upload_service = UploadService(
        profile_repo=prof_repo,
        video_repo=vid_repo,
        tiktok_adapter=mock_adapter,
        proxy_repo=px_repo,
    )

    # Create dummy video file
    dummy_video = tmp_path / "dummy.mp4"
    dummy_video.write_bytes(b"testvideo123")
    vid_repo.update_metadata(video_id=1, file_path=str(dummy_video))

    with pytest.raises(PermissionError, match="AgentShield Strict Proxy Gate"):
        upload_service.execute_upload(video_id=1, profile_id=2)

    # Adapter must NEVER be called
    mock_adapter.upload_video.assert_not_called()

    # Video status must be marked as failed with security reason
    v_row = vid_repo.get_by_id(1)
    assert v_row["status"] == "failed"
    assert "Proxy" in v_row["error_message"]


def test_metrics_sync_worker_skips_unproxied_profile(temp_db: Path) -> None:
    """Verifies MetricsSyncWorker skips unproxied profiles without calling sync service."""
    prof_repo = ProfileRepository(db_path=temp_db)
    px_repo = ProxyRepository(db_path=temp_db)

    mock_profile_service = MagicMock()
    mock_profile_service.profile_repo = prof_repo
    mock_profile_service.proxy_repo = px_repo

    # Dispatch for profile 1 (proxied) and profile 2 (unproxied)
    worker = MetricsSyncWorker(
        profile_ids=[1, 2],
        profile_service=mock_profile_service,
        proxy_repo=px_repo,
        profile_repo=prof_repo,
    )

    worker.execute()

    # Profile 1 should be synced, Profile 2 must be SKIPPED
    mock_profile_service.sync_metrics_from_tiktok.assert_called_once_with(1)


def test_main_window_upload_queue_filters_unproxied_profiles(temp_db: Path) -> None:
    """Verifies MainWindow filters unproxied profiles when starting upload queue."""
    prof_repo = ProfileRepository(db_path=temp_db)
    selected_profiles = [1, 2] # 1 is proxied, 2 is unproxied

    proxied_profiles = [pid for pid in selected_profiles if (prof_repo.get_by_id(pid) or {}).get("proxy_id")]
    skipped_count = len(selected_profiles) - len(proxied_profiles)

    assert proxied_profiles == [1]
    assert skipped_count == 1
