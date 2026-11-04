"""
End-to-End integration test validating the entire operational lifecycle:
Database -> Proxies & Leak Guard -> Projects -> Profiles -> Queue & Concurrency -> Upload & Aggregates.
Strict TDD - Phase 2 (RED)
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication
from sammonny import ProxyHealthResult, RemoteStatus, UploadResult
from src.application.services.profile_service import ProfileService
from src.application.services.proxy_service import ProxyService
from src.application.services.upload_service import UploadService
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
from src.infrastructure.database.repositories.video_repository import VideoRepository
from src.presentation.views.main_window import TikTokManagerMainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_end_to_end_operational_lifecycle(qapp):
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "e2e_app.db"
        run_all_migrations(db_path)

        # Repositories
        project_repo = ProjectRepository(db_path)
        proxy_repo = ProxyRepository(db_path)
        profile_repo = ProfileRepository(db_path)
        video_repo = VideoRepository(db_path)

        # 1. Create Project
        proj_id = project_repo.create(name="Summer 2026 Campaign", description="Viral videos")
        assert proj_id > 0

        # 2. Bulk import proxies (including local leak IP)
        raw_proxies = [
            "103.20.5.10:8080:u1:p1",
            "103.20.5.11:8080:u2:p2",
            "127.0.0.1:8080:leak:leak",  # Leak
        ]
        imported = proxy_repo.bulk_import(raw_proxies)
        assert imported == 3

        # 3. Check proxies via ProxyService with simulated health responses
        proxy_service = ProxyService(proxy_repo=proxy_repo)
        all_proxies = proxy_repo.list_all()

        def mock_health_check(item):
            if "127.0.0.1" in item.host:
                return ProxyHealthResult(is_alive=True, latency_ms=10.0, egress_ip="127.0.0.1")
            return ProxyHealthResult(is_alive=True, latency_ms=65.0, egress_ip=item.host, country="US")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("sammonny.check_proxy_health", mock_health_check)
            for p in all_proxies:
                proxy_service.check_proxy(p["id"])

        # Verify leak was detected and marked
        leak_p = [p for p in proxy_repo.list_all() if "127.0.0.1" in p["host"]][0]
        assert leak_p["status"] == "leak_detected"

        good_p = [p for p in proxy_repo.list_all() if p["status"] == "alive"][0]
        assert good_p["country_code"] == "US"

        # 4. Create Profiles and bind proxy
        profile_service = ProfileService(profile_repo=profile_repo, proxy_repo=proxy_repo)
        prof_1 = profile_repo.create(
            {
                "name": "Summer_Creator_01",
                "project_id": proj_id,
                "storage_dir": "profiles/p1",
                "user_agent": "Mozilla/5.0 Chrome/130",
                "status": "LIVE",
            }
        )
        profile_service.assign_proxy(prof_1, good_p["id"])

        # Attempting to assign leak proxy must raise ValueError
        with pytest.raises(ValueError, match="LEAK DETECTED"):
            profile_service.assign_proxy(prof_1, leak_p["id"])

        # 5. Enqueue & Upload Video
        mock_adapter = MagicMock()
        mock_adapter.upload_video.return_value = UploadResult(
            success=True,
            draft_id="draft_e2e_01",
            publish_id="v_pub_tiktok_summer_01",
            status=RemoteStatus.PROCESSING_UPLOAD,
            bytes_uploaded=4096,
            total_bytes=4096,
        )

        upload_service = UploadService(
            profile_repo=profile_repo,
            video_repo=video_repo,
            tiktok_adapter=mock_adapter,
        )

        # Create dummy video
        video_file = Path(tmpdir) / "summer_clip.mp4"
        video_file.write_bytes(b"\x00" * 4096)

        video_id = upload_service.enqueue_video(
            file_path=video_file,
            title="Summer Beach Vibes #summer",
            duration_sec=12.0,
        )
        assert video_id > 0

        # Execute upload
        upload_res = upload_service.execute_upload(video_id=video_id, profile_id=prof_1)
        assert upload_res.success is True
        assert upload_res.publish_id == "v_pub_tiktok_summer_01"

        # 6. Verify Main Window loads all records without exception
        main_win = TikTokManagerMainWindow(db_path=db_path)
        assert main_win.profile_table.rowCount() >= 1
        main_win.close()
