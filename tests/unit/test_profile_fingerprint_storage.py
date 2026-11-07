"""Every created profile stores its own fixed fingerprint (profiles.fingerprint_json + mirror columns)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from src.domain.fingerprint.browser_fingerprint import generate_fingerprint
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository

DAEMON_FP = {
    "os": "win",
    "navigator": {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36",
        "platform": "Win32",
        "hardware_concurrency": 12,
        "device_memory": 8,
        "languages": ["vi-VN"],
    },
    "screen": {"width": 1920, "height": 1080, "color_depth": 24, "pixel_ratio": 1},
    "webgl": {"vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics)"},
    "canvas_noise": 5.13404848041,
    "audio_noise": 6.29026638229112e-07,
    "webgl_noise": 89.365958,
    "timezone": {"mode": "auto", "timezone_id": "Asia/Bangkok"},
}


@pytest.fixture
def repo(tmp_path: Path) -> ProfileRepository:
    db = tmp_path / "fp.db"
    run_all_migrations(db)
    return ProfileRepository(db)


def test_new_profiles_get_distinct_fixed_fingerprints(repo: ProfileRepository) -> None:
    a = repo.get_by_id(repo.create({"name": "a", "uuid": "uuid-a"}))
    b = repo.get_by_id(repo.create({"name": "b", "uuid": "uuid-b"}))
    fa, fb = json.loads(a["fingerprint_json"]), json.loads(b["fingerprint_json"])
    assert fa == generate_fingerprint("uuid-a") and fb == generate_fingerprint("uuid-b")
    assert a["user_agent"] == fa["navigator"]["user_agent"] and "Chrome/" in a["user_agent"]
    assert a["canvas_noise"] != b["canvas_noise"]
    assert a["webgl_renderer"] == fa["webgl"]["renderer"]


def test_a_given_fingerprint_is_kept_and_mirrored(repo: ProfileRepository) -> None:
    p = repo.get_by_id(repo.create({"name": "d", "uuid": "uuid-d", "fingerprint_json": json.dumps(DAEMON_FP)}))
    assert json.loads(p["fingerprint_json"]) == DAEMON_FP
    assert p["cpu_cores"] == 12 and p["webgl_vendor"] == "Google Inc. (Intel)" and p["timezone_id"] == "Asia/Bangkok"


def test_daemon_created_profile_stores_the_daemons_fingerprint(tmp_path: Path) -> None:
    from src.application.services.gologin_sync_service import GoLoginSyncService

    db = tmp_path / "d.db"
    run_all_migrations(db)
    profiles = ProfileRepository(db)
    gl = MagicMock()
    gl.create.return_value = "uuid-daemon-1"
    gl.client.get_profile.return_value = MagicMock(raw_data={"id": "uuid-daemon-1", "fingerprint": DAEMON_FP})
    svc = GoLoginSyncService(profile_repo=profiles, project_repo=ProjectRepository(db), proxy_repo=ProxyRepository(db))
    svc.daemon_supervisor = MagicMock()
    with (
        patch("sammonny.gologin.gologin.GoLogin", return_value=gl),
        patch(
            "src.infrastructure.browser.orbita_launcher.OrbitaLauncher.resolve_profile_dir",
            return_value=tmp_path / "prof",
        ),
    ):
        pid = svc.create_real_gologin_profile(name="acc daemon")
    p = profiles.get_by_id(pid)
    assert json.loads(p["fingerprint_json"]) == DAEMON_FP
    assert p["user_agent"] == DAEMON_FP["navigator"]["user_agent"]
    assert p["canvas_noise"] == DAEMON_FP["canvas_noise"]


def test_daemon_without_fingerprint_falls_back_to_a_unique_local_one(tmp_path: Path) -> None:
    from src.application.services.gologin_sync_service import GoLoginSyncService

    db = tmp_path / "e.db"
    run_all_migrations(db)
    profiles = ProfileRepository(db)
    gl = MagicMock()
    gl.create.return_value = "uuid-daemon-2"
    gl.client.get_profile.side_effect = RuntimeError("daemon record unavailable")
    svc = GoLoginSyncService(profile_repo=profiles, project_repo=ProjectRepository(db), proxy_repo=ProxyRepository(db))
    svc.daemon_supervisor = MagicMock()
    with (
        patch("sammonny.gologin.gologin.GoLogin", return_value=gl),
        patch(
            "src.infrastructure.browser.orbita_launcher.OrbitaLauncher.resolve_profile_dir",
            return_value=tmp_path / "prof2",
        ),
    ):
        pid = svc.create_real_gologin_profile(name="acc local fp")
    p = profiles.get_by_id(pid)
    assert json.loads(p["fingerprint_json"]) == generate_fingerprint("uuid-daemon-2")
