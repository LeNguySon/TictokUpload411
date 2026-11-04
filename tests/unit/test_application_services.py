"""
Unit tests for Application Services: ProxyService, UploadService, ProfileService.
Strict TDD - Phase 2 (RED)
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sammonny import ProxyHealthResult, RemoteStatus, UploadResult
from src.application.services.profile_service import ProfileService
from src.application.services.proxy_service import ProxyService
from src.application.services.upload_service import UploadService
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
from src.infrastructure.database.repositories.video_repository import VideoRepository


@pytest.fixture
def service_context():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "services_test.db"
        run_all_migrations(db_path)

        project_repo = ProjectRepository(db_path)
        profile_repo = ProfileRepository(db_path)
        proxy_repo = ProxyRepository(db_path)
        video_repo = VideoRepository(db_path)

        # Create dummy project
        proj_id = project_repo.create(name="Beta Campaign")

        yield {
            "db_path": db_path,
            "project_repo": project_repo,
            "profile_repo": profile_repo,
            "proxy_repo": proxy_repo,
            "video_repo": video_repo,
            "project_id": proj_id,
        }


def test_proxy_service_health_check_and_leak_detection(service_context):
    proxy_repo = service_context["proxy_repo"]
    proxy_repo.bulk_import(["103.20.5.10:8080:u1:p1"])
    proxies = proxy_repo.list_all()
    proxy_id = proxies[0]["id"]

    proxy_service = ProxyService(proxy_repo=proxy_repo)

    # 1. Normal alive check
    mock_health = ProxyHealthResult(
        is_alive=True,
        latency_ms=85.0,
        egress_ip="103.20.5.10",
        country="VN",
        city="Hanoi",
    )
    with patch("sammonny.check_proxy_health", return_value=mock_health):
        res = proxy_service.check_proxy(proxy_id)
        assert res.is_alive is True
        p = proxy_repo.get_by_id(proxy_id)
        assert p["status"] == "alive"
        assert p["country_code"] == "VN"

    # 2. Leak detected check
    mock_leak = ProxyHealthResult(
        is_alive=True,
        latency_ms=20.0,
        egress_ip="127.0.0.1",  # Local machine IP
    )
    with patch("sammonny.check_proxy_health", return_value=mock_leak):
        res_leak = proxy_service.check_proxy(proxy_id)
        assert res_leak.is_alive is False
        p_leak = proxy_repo.get_by_id(proxy_id)
        assert p_leak["status"] == "leak_detected"


def test_upload_service_orchestration(service_context):
    profile_repo = service_context["profile_repo"]
    video_repo = service_context["video_repo"]
    project_id = service_context["project_id"]

    profile_id = profile_repo.create(
        {
            "name": "TikTok_Star_01",
            "project_id": project_id,
            "storage_dir": "C:/profiles/p1",
            "user_agent": "Mozilla/5.0 Chrome/130",
            "status": "LIVE",
        }
    )

    # Create dummy video file
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(b"\x00" * 4096)
        video_path = f.name

    try:
        mock_adapter = MagicMock()
        mock_adapter.upload_video.return_value = UploadResult(
            success=True,
            draft_id="draft_abc",
            publish_id="v_pub_tiktok_777",
            status=RemoteStatus.PROCESSING_UPLOAD,
            bytes_uploaded=4096,
            total_bytes=4096,
        )

        upload_service = UploadService(
            profile_repo=profile_repo,
            video_repo=video_repo,
            tiktok_adapter=mock_adapter,
        )

        # 1. Enqueue video
        video_id = upload_service.enqueue_video(
            file_path=video_path,
            title="My Test Upload #viral",
            duration_sec=15.0,
        )
        assert video_id > 0

        # 2. Execute upload
        job_result = upload_service.execute_upload(video_id=video_id, profile_id=profile_id)
        assert job_result.success is True
        assert job_result.publish_id == "v_pub_tiktok_777"

        # Check DB status
        v = video_repo.get_by_id(video_id)
        assert v["status"] == "published"
        assert v["tiktok_video_id"] == "v_pub_tiktok_777"
    finally:
        Path(video_path).unlink(missing_ok=True)


def test_profile_service_operations(service_context):
    profile_repo = service_context["profile_repo"]
    proxy_repo = service_context["proxy_repo"]
    project_repo = service_context["project_repo"]
    project_id = service_context["project_id"]

    # Create target project
    target_proj_id = project_repo.create(name="Target Campaign")

    # Create profile
    profile_id = profile_repo.create(
        {
            "name": "MMO_Profile_02",
            "project_id": project_id,
            "storage_dir": "C:/profiles/p2",
            "user_agent": "Mozilla/5.0 Chrome/130",
            "status": "LIVE",
        }
    )

    # Create proxy and proxy with leak
    proxy_repo.bulk_import(["10.0.0.1:8080:u:p", "10.0.0.2:8080:u:p"])
    proxies = proxy_repo.list_all()
    good_proxy_id = proxies[0]["id"]
    leak_proxy_id = proxies[1]["id"]
    proxy_repo.mark_ip_leak(leak_proxy_id, "Host IP leaked!")

    mock_adapter = MagicMock()
    mock_adapter.fetch_creator_metrics.return_value = {
        "creator_username": "viral_queen",
        "creator_nickname": "Queen",
    }

    profile_service = ProfileService(
        profile_repo=profile_repo,
        proxy_repo=proxy_repo,
        tiktok_adapter=mock_adapter,
    )

    # 1. Sync metrics
    creator_info = profile_service.sync_metrics_from_tiktok(profile_id)
    assert creator_info["creator_username"] == "viral_queen"
    updated_p = profile_repo.get_by_id(profile_id)
    assert updated_p["username_on_tiktok"] == "viral_queen"

    # 2. Assign good proxy
    ok = profile_service.assign_proxy(profile_id=profile_id, proxy_id=good_proxy_id)
    assert ok is True
    assert profile_repo.get_by_id(profile_id)["proxy_id"] == good_proxy_id

    # 3. Assign leak proxy should fail with ValueError
    with pytest.raises(ValueError, match="LEAK DETECTED"):
        profile_service.assign_proxy(profile_id=profile_id, proxy_id=leak_proxy_id)

    # 4. Move to project
    moved_count = profile_service.move_profiles_to_project([profile_id], target_proj_id)
    assert moved_count == 1
    assert profile_repo.get_by_id(profile_id)["project_id"] == target_proj_id

    # 5. Trash and restore
    assert profile_service.trash_profile(profile_id) is True
    assert profile_repo.get_by_id(profile_id)["is_trashed"] == 1
    assert profile_service.restore_profile(profile_id) is True
    assert profile_repo.get_by_id(profile_id)["is_trashed"] == 0
