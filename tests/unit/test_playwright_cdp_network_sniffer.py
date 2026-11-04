"""TDD Unit Test Suite for Playwright / CDP Network Sniffer Attachment.
Conforms to ECC Development Standards.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from src.application.signals.app_signals import AppSignalBus
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.tiktok.network_sniffer import (
    attach_playwright_sniffer,
)


@pytest.fixture
def db_env(tmp_path: Path):
    db_file = tmp_path / "cdp_sniffer_test.db"
    run_all_migrations(db_file)
    repo = ProfileRepository(db_file)
    signal_bus = AppSignalBus.instance()
    return {
        "db_file": db_file,
        "repo": repo,
        "signal_bus": signal_bus,
    }


def test_attach_playwright_sniffer_processes_tiktok_api(db_env):
    repo: ProfileRepository = db_env["repo"]
    db_file = db_env["db_file"]
    signal_bus = db_env["signal_bus"]

    pid = repo.create({"name": "CDP_User"})

    mock_page = MagicMock()
    listeners = {}

    def mock_on(event_name, handler):
        listeners[event_name] = handler

    mock_page.on.side_effect = mock_on

    # Attach sniffer
    attach_playwright_sniffer(
        context_or_page=mock_page,
        profile_id=pid,
        db_path=db_file,
        signal_bus=signal_bus,
    )

    assert "response" in listeners
    on_response = listeners["response"]

    # 1. Non-matching URL (ignored)
    ign_resp = MagicMock()
    ign_resp.url = "https://fonts.googleapis.com/css2"
    ign_resp.status = 200
    on_response(ign_resp)
    assert repo.get_by_id(pid)["username_on_tiktok"] is None

    # 2. Status 500 (ignored)
    err_resp = MagicMock()
    err_resp.url = "https://www.tiktok.com/api/user/detail/?uniqueId=failed"
    err_resp.status = 500
    on_response(err_resp)
    assert repo.get_by_id(pid)["username_on_tiktok"] is None

    # 3. Matching TikTok API Response (processed)
    ok_resp = MagicMock()
    ok_resp.url = "https://www.tiktok.com/api/user/detail/?uniqueId=cdp_master"
    ok_resp.status = 200
    ok_resp.json.return_value = {
        "userInfo": {
            "user": {
                "id": "999888777",
                "uniqueId": "cdp_master",
                "nickname": "Master CDP",
            },
            "stats": {
                "followerCount": 88000,
            },
        }
    }

    on_response(ok_resp)

    # Verify profile was updated in SQLite
    prof = repo.get_by_id(pid)
    assert prof["username_on_tiktok"] == "cdp_master"
    assert prof["nickname"] == "Master CDP"
    assert prof["total_followers"] == 88000
