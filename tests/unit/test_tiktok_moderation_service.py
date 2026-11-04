"""Unit tests for TikTokModerationService and AccountHealthDialog.
Validates:
1. TikTokModerationService.fetch_account_standing parses API responses and updates profiles.
2. TikTokModerationService.fetch_video_violations upserts violation records into violateVideos.
3. AccountHealthDialog renders 4 KPI cards and populates video violation table.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QApplication
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.tiktok.moderation_service import TikTokModerationService
from src.presentation.dialogs.account_health_dialog import AccountHealthDialog


@pytest.fixture
def app_instance():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


@pytest.fixture
def isolated_db(tmp_path: Path):
    db_file = tmp_path / "moderation_test.db"
    run_all_migrations(db_file)
    prof_repo = ProfileRepository(db_file)
    p_id = prof_repo.create(
        {
            "name": "HealthTestProfile",
            "username_on_tiktok": "health.tester",
            "cookies_json": '[{"name": "sessionid", "value": "test_session_123"}]',
            "status": "LIVE",
        }
    )
    return {"db_file": db_file, "prof_repo": prof_repo, "p_id": p_id}


def test_fetch_account_standing_good(isolated_db):
    """Verifies that Good standing with 0 strikes updates profile and returns clean metrics."""
    service = TikTokModerationService(db_path=isolated_db["db_file"])
    p_id = isolated_db["p_id"]

    mock_resp = {
        "status_code": 0,
        "standing_level": "Good",
        "active_strikes": 0,
        "restricted_features": [],
    }

    with patch.object(service, "_request_tiktok_api", return_value=mock_resp):
        res = service.fetch_account_standing(p_id)
        assert res["ok"] is True
        assert res["account_standing"] == "Good"
        assert res["strike_count"] == 0
        assert "tốt" in res["status_label"].lower()

    prof = isolated_db["prof_repo"].get_by_id(p_id)
    assert prof["account_standing"] == "Good"
    assert prof["strike_count"] == 0


def test_fetch_account_standing_warning_strikes(isolated_db):
    """Verifies that Warning standing with 1 strike updates profile."""
    service = TikTokModerationService(db_path=isolated_db["db_file"])
    p_id = isolated_db["p_id"]

    mock_resp = {
        "status_code": 0,
        "standing_level": "Warning",
        "active_strikes": 1,
        "restricted_features": ["live_stream"],
    }

    with patch.object(service, "_request_tiktok_api", return_value=mock_resp):
        res = service.fetch_account_standing(p_id)
        assert res["ok"] is True
        assert res["account_standing"] == "Warning"
        assert res["strike_count"] == 1
        assert "Cảnh báo" in res["status_label"]

    prof = isolated_db["prof_repo"].get_by_id(p_id)
    assert prof["account_standing"] == "Warning"
    assert prof["strike_count"] == 1


def test_fetch_video_violations_upsert(isolated_db):
    """Verifies that video violations (including originality strikes) are upserted into violateVideos."""
    service = TikTokModerationService(db_path=isolated_db["db_file"])
    p_id = isolated_db["p_id"]

    mock_resp = {
        "status_code": 0,
        "violation_list": [
            {
                "item_id": "7198273918237192",
                "title": "Meme Reaction Video #1",
                "violation_title": "Gậy Nguyên Tác (Unoriginal Content - Ineligible for FYP)",
                "violation_reason": "Nội dung biên tập lại không tạo thêm giá trị nguyên bản sáng tạo.",
                "create_time": "2026-11-01 10:00:00",
                "appeal_deadline": "2026-11-15 23:59:59",
                "status": "pending",
            },
            {
                "item_id": "7198273918237193",
                "title": "Dance Cover #2",
                "violation_title": "Bản quyền âm thanh (Sound Muted)",
                "violation_reason": "Âm thanh bị tắt tiếng do vi phạm bản quyền thương mại.",
                "create_time": "2026-11-02 14:00:00",
                "appeal_deadline": "2026-11-16 23:59:59",
                "status": "appealed",
            },
        ],
    }

    with patch.object(service, "_request_tiktok_api", return_value=mock_resp):
        v_list = service.fetch_video_violations(p_id)
        assert len(v_list) == 2
        assert v_list[0]["video_id"] == "7198273918237192"
        assert "Gậy Nguyên Tác" in v_list[0]["violate_title"]

    # Verify rows in database
    import sqlite3

    conn = sqlite3.connect(isolated_db["db_file"])
    rows = conn.execute(
        "SELECT video_id, violate_title, status FROM violateVideos WHERE profile_id=? ORDER BY id ASC",
        (p_id,),
    ).fetchall()
    conn.close()
    assert len(rows) == 2
    assert rows[0][0] == "7198273918237192"
    assert rows[1][0] == "7198273918237193"


def test_account_health_dialog_renders_correctly(isolated_db, app_instance):
    """Verifies that AccountHealthDialog instantiates, populates cards and table."""
    p_id = isolated_db["p_id"]

    # Prepopulate a violation in DB
    import sqlite3

    conn = sqlite3.connect(isolated_db["db_file"])
    conn.execute(
        """
        INSERT INTO violateVideos (profile_id, video_id, title, violate_title, violate_description, appeal_date, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            p_id,
            "789123456",
            "Test Unoriginal Video",
            "Gậy Nguyên Tác",
            "Không đạt tính nguyên bản",
            "2026-11-20",
            "pending",
        ),
    )
    conn.execute("UPDATE profiles SET account_standing='Warning', strike_count=1 WHERE id=?", (p_id,))
    conn.commit()
    conn.close()

    dialog = AccountHealthDialog(profile_id=p_id, db_path=isolated_db["db_file"])
    assert dialog.profile_id == p_id
    assert dialog.card_standing.value_label.text() == "Warning"
    assert dialog.card_strikes.value_label.text() == "1 / 3 Gậy"
    assert dialog.table_violate.rowCount() == 1
    assert dialog.table_violate.item(0, 0).text() == "789123456"
    assert "Gậy Nguyên Tác" in dialog.table_violate.item(0, 2).text()
    dialog.close()
    dialog.deleteLater()


def test_main_window_account_health_action_integration(isolated_db, app_instance):
    """Verifies that MainWindow triggers AccountHealthDialog when requested."""
    from src.presentation.views.main_window import TikTokManagerMainWindow

    p_id = isolated_db["p_id"]
    with (
        patch("src.presentation.views.main_window.setTheme"),
        patch("src.presentation.views.main_window.MetricsSyncWorker"),
        patch("src.presentation.dialogs.account_health_dialog.AccountHealthDialog.exec") as mock_exec,
    ):
        win = TikTokManagerMainWindow(db_path=isolated_db["db_file"])
        win._on_open_account_health(p_id)
        assert mock_exec.called

        win.scheduler_timer.stop()
        if hasattr(win, "profile_status_timer"):
            win.profile_status_timer.stop()
        win.profile_table.clearSelection()
        win.close()
        win.deleteLater()
        app_instance.processEvents()


def test_parse_cookie_header_with_dpapi():
    """Verifies that parse_cookie_header_str decrypts DPAPI-protected cookies seamlessly."""
    from src.infrastructure.credentials.dpapi import protect_text
    from src.infrastructure.tiktok.moderation_service import parse_cookie_header_str

    raw_cookies = '[{"name": "sessionid", "value": "encrypted_val_999"}, {"name": "ttwid", "value": "ttwid_token"}]'
    dpapi_encrypted = protect_text(raw_cookies)
    assert dpapi_encrypted.startswith("gloglin:dpapi:v1:")

    cookie_hdr = parse_cookie_header_str(dpapi_encrypted)
    assert "sessionid=encrypted_val_999" in cookie_hdr
    assert "ttwid=ttwid_token" in cookie_hdr
