"""
Unit tests for SamMonny SDK & GoLogin Real Profile Integration.
Strict TDD - Phase 2
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from src.infrastructure.browser.orbita_launcher import OrbitaLauncher
from src.infrastructure.browser.sammonny_daemon_manager import SamMonnyDaemonSupervisor
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository


@pytest.fixture
def supervisor():
    return SamMonnyDaemonSupervisor()


@pytest.fixture
def temp_db(tmp_path: Path):
    db_file = tmp_path / "test_gologin_sync.db"
    run_all_migrations(db_file)
    return db_file


def test_orbita_launcher_finds_real_orbita_executable():
    launcher = OrbitaLauncher()
    exe = launcher.executable_path

    # Must resolve to an existing executable, prioritizing orbita-152 / orbita-139
    assert exe is not None
    assert exe.exists()
    assert "chrome.exe" in exe.name.lower() or "orbita" in str(exe).lower()


def test_daemon_supervisor_detects_binary_path(supervisor, tmp_path):
    # Hermetic: the first existing candidate wins (no dependency on a daemon installed on this machine).
    missing = tmp_path / "missing" / "sammonny-daemon.exe"
    installed = tmp_path / "engine" / "sammonny-daemon.exe"
    installed.parent.mkdir()
    installed.write_bytes(b"MZ")
    with patch(
        "src.infrastructure.browser.sammonny_daemon_manager.daemon_binary_candidates",
        return_value=[missing, installed],
    ):
        bin_path = supervisor.find_daemon_binary()
    assert bin_path == installed
    assert bin_path.name == "sammonny-daemon.exe"

    with patch(
        "src.infrastructure.browser.sammonny_daemon_manager.daemon_binary_candidates", return_value=[missing]
    ):
        assert supervisor.find_daemon_binary() is None


def test_daemon_supervisor_check_health(supervisor):
    # Tests health checking mechanism (either live or mocked)
    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"status": "healthy"}'
        mock_resp.getcode.return_value = 200
        mock_url.return_value.__enter__.return_value = mock_resp

        health = supervisor.check_health()
        assert health["daemon_7654"] is True


def test_sync_real_gologin_profiles(temp_db):
    prof_repo = ProfileRepository(temp_db)
    proj_repo = ProjectRepository(temp_db)

    # Mock real GoLogin profiles list
    mock_gologin_profiles = [
        {
            "id": "mock-uuid-001",
            "name": "Profile-Test-Real-1",
            "notes": "TikTok MMO Account 1",
            "fingerprint": {
                "navigator": {"user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/152.0.0.0"},
                "webgl": {"vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel)"},
                "canvas_noise": 5.4,
                "audio_noise": 0.0001,
            },
        },
        {
            "id": "mock-uuid-002",
            "name": "Profile-Test-Real-2",
            "notes": "TikTok MMO Account 2",
            "fingerprint": {
                "navigator": {"user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/139.0.0.0"},
                "webgl": {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA)"},
                "canvas_noise": 7.2,
                "audio_noise": 0.0002,
            },
        },
    ]

    from src.application.services.gologin_sync_service import GoLoginSyncService

    sync_service = GoLoginSyncService(profile_repo=prof_repo, project_repo=proj_repo)
    synced_count = sync_service.sync_profiles_list(mock_gologin_profiles)

    assert synced_count == 2
    profiles = prof_repo.list_active()
    assert len(profiles) == 2

    p1 = prof_repo.get_by_uuid("mock-uuid-001")
    assert p1 is not None
    assert p1["name"] == "Profile-Test-Real-1"
    assert "Chrome/152" in p1["user_agent"]
    assert p1["canvas_noise"] == 5.4

    # Idempotent re-sync test
    synced_count_2 = sync_service.sync_profiles_list(mock_gologin_profiles)
    assert synced_count_2 == 2
    assert len(prof_repo.list_active()) == 2
