"""
Unit tests for Repositories: ProjectRepository, ProxyRepository, ProfileRepository, and VideoRepository.
"""

import tempfile
from pathlib import Path

import pytest
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository, parse_proxy_line
from src.infrastructure.database.repositories.video_repository import VideoRepository


@pytest.fixture
def test_db():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "repo_test.db"
        run_all_migrations(db_path)
        yield db_path


# -----------------------------------------------------------------------------
# 1. ProjectRepository Tests
# -----------------------------------------------------------------------------
def test_project_crud_and_safe_delete(test_db):
    repo = ProjectRepository(test_db)

    # 1. Default project must exist
    projects = repo.list_all()
    assert len(projects) >= 1
    assert projects[0]["name"] == "Dự án mặc định"

    # 2. Create new project
    proj_id = repo.create(name="US_Beta_Campaign", description="US Niche 2026", color="#107C41")
    assert proj_id > 1

    # 3. Retrieve
    p = repo.get_by_id(proj_id)
    assert p is not None
    assert p["name"] == "US_Beta_Campaign"
    assert p["color"] == "#107C41"

    # 4. Attach profile and test safe delete (profile must survive with project_id = NULL)
    prof_repo = ProfileRepository(test_db)
    prof_id = prof_repo.create(
        {
            "uuid": "u-123",
            "name": "Profile 1",
            "storage_dir": "/p1",
            "user_agent": "Mozilla/5.0",
            "project_id": proj_id,
        }
    )

    # Delete project
    repo.delete(proj_id)
    assert repo.get_by_id(proj_id) is None

    # Profile should now have project_id is None
    prof = prof_repo.get_by_id(prof_id)
    assert prof is not None
    assert prof["project_id"] is None


# -----------------------------------------------------------------------------
# 2. ProxyRepository & Smart Parser Tests
# -----------------------------------------------------------------------------
def test_proxy_smart_parser():
    # Format 1: host:port:user:pass
    p1 = parse_proxy_line("192.168.1.100:8080:alice:secret123")
    assert p1 == ("192.168.1.100", 8080, "alice", "secret123", "http", None)

    # Format 2: user:pass@host:port
    p2 = parse_proxy_line("bob:mypass@10.0.0.5:9050")
    assert p2 == ("10.0.0.5", 9050, "bob", "mypass", "http", None)

    # Format 3: protocol://user:pass@host:port
    p3 = parse_proxy_line("socks5://charlie:p4ss@172.16.0.2:1080")
    assert p3 == ("172.16.0.2", 1080, "charlie", "p4ss", "socks5", None)

    # Format 4: host:port
    p4 = parse_proxy_line("1.1.1.1:3128")
    assert p4 == ("1.1.1.1", 3128, None, None, "http", None)

    # Format 5: host:port:user:pass:change_ip_url
    p5 = parse_proxy_line("2.2.2.2:8080:u1:p1:https://proxy.net/rotate")
    assert p5 == ("2.2.2.2", 8080, "u1", "p1", "http", "https://proxy.net/rotate")


def test_proxy_bulk_import_and_leak_prevention(test_db):
    repo = ProxyRepository(test_db)
    raw_lines = [
        "192.168.1.100:8080:user1:pass1",
        "10.0.0.5:9050:user2:pass2",
        "invalid_proxy_line",  # Should be skipped safely
        "192.168.1.100:8080:user1:pass1",  # Duplicate, should not crash
    ]

    imported_count = repo.bulk_import(raw_lines)
    assert imported_count == 2

    proxies = repo.list_all()
    assert len(proxies) == 2

    # Test marking IP leak
    target_id = proxies[0]["id"]
    repo.mark_ip_leak(target_id, error_msg="Outbound IP matched local machine IP!")

    updated = repo.get_by_id(target_id)
    assert updated["status"] == "leak_detected"
    assert "matched local machine" in updated["error_message"]


# -----------------------------------------------------------------------------
# 3. ProfileRepository & Bulk Assignment Tests
# -----------------------------------------------------------------------------
def test_profile_mmo_crud_and_bulk_move(test_db):
    prof_repo = ProfileRepository(test_db)
    proj_repo = ProjectRepository(test_db)

    p1_id = proj_repo.create(name="Project Alpha", color="#FF0000")
    p2_id = proj_repo.create(name="Project Beta", color="#00FF00")

    # Create 2 profiles
    prof1_id = prof_repo.create(
        {
            "uuid": "prof-uuid-1",
            "name": "US_Channel_01",
            "storage_dir": "/storage/1",
            "user_agent": "Mozilla/5.0",
            "project_id": p1_id,
            "username_on_tiktok": "@channel01",
            "money_earned": 250.50,
            "views_month": 45000,
            "status": "LIVE",
        }
    )
    prof2_id = prof_repo.create(
        {
            "uuid": "prof-uuid-2",
            "name": "US_Channel_02",
            "storage_dir": "/storage/2",
            "user_agent": "Mozilla/5.0",
            "project_id": p1_id,
            "username_on_tiktok": "@channel02",
            "money_earned": 120.00,
            "views_month": 12000,
            "status": "LIVE",
        }
    )

    # Bulk move from Project Alpha to Project Beta
    prof_repo.bulk_assign_project([prof1_id, prof2_id], p2_id)

    prof1 = prof_repo.get_by_id(prof1_id)
    prof2 = prof_repo.get_by_id(prof2_id)
    assert prof1["project_id"] == p2_id
    assert prof2["project_id"] == p2_id

    # Test soft-delete
    prof_repo.soft_delete(prof1_id)
    active_profiles = prof_repo.list_active()
    assert len(active_profiles) == 1
    assert active_profiles[0]["id"] == prof2_id

    # Test restore
    prof_repo.restore(prof1_id)
    assert len(prof_repo.list_active()) == 2


# -----------------------------------------------------------------------------
# 4. VideoRepository & Atomic SHA-256 Deduplication
# -----------------------------------------------------------------------------
def test_video_registry_atomic_reservation(test_db):
    video_repo = VideoRepository(test_db)
    prof_repo = ProfileRepository(test_db)
    v_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    # Create 2 valid profiles for foreign key adherence
    prof1_id = prof_repo.create(
        {
            "uuid": "v-prof-1",
            "name": "Bot Profile 1",
            "storage_dir": "/s/1",
            "user_agent": "Mozilla/5.0",
        }
    )
    prof2_id = prof_repo.create(
        {
            "uuid": "v-prof-2",
            "name": "Bot Profile 2",
            "storage_dir": "/s/2",
            "user_agent": "Mozilla/5.0",
        }
    )

    # 1. Register video file
    video_id = video_repo.register_or_update(
        video_hash=v_hash,
        file_path="/videos/recipe_01.mp4",
        file_name="recipe_01.mp4",
        file_size=15420000,
        mtime=1700000000.0,
    )
    assert video_id > 0

    # 2. Reserve video for Profile 1
    reserved = video_repo.try_reserve(video_id, assigned_profile_id=prof1_id)
    assert reserved is True

    # 3. Second attempt to reserve the same video for Profile 2 must FAIL (prevent double upload)
    reserved_again = video_repo.try_reserve(video_id, assigned_profile_id=prof2_id)
    assert reserved_again is False

    # 4. Update status to published
    video_repo.mark_published(video_id, published_profile_id=prof1_id, tiktok_video_id="tt_video_998877")
    v = video_repo.get_by_id(video_id)
    assert v["status"] == "published"
    assert v["tiktok_video_id"] == "tt_video_998877"
