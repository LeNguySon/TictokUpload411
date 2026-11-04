"""Unit tests for Video Violation Appeals, Creator Rewards Re-apply, and GoLogin TikTok Client.
Strict ECC TDD: Validates business logic, database mutations, and UI dialog integration.
"""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QApplication
from src.infrastructure.credentials.dpapi import protect_text
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository


@pytest.fixture
def app_instance():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


@pytest.fixture
def isolated_env(tmp_path: Path):
    db_file = tmp_path / "appeal_reapply_test.db"
    run_all_migrations(db_file)

    proxy_repo = ProxyRepository(db_file)
    proxy_id = proxy_repo.create(
        host="118.70.171.85",
        port=46796,
        username="fttMws",
        password="secret_password",
        protocol="http",
    )

    prof_repo = ProfileRepository(db_file)
    raw_cookies = '[{"name": "sessionid", "value": "test_session_token_xyz"}, {"name": "passport_csrf_token", "value": "csrf_123"}]'
    enc_cookies = protect_text(raw_cookies)

    profile_id = prof_repo.create(
        {
            "name": "CreatorAppealChannel",
            "uuid": "uuid-test-appeal-1234",
            "username_on_tiktok": "creator.appeal",
            "cookies_json": enc_cookies,
            "proxy_id": proxy_id,
            "status": "LIVE",
            "account_standing": "Warning",
            "strike_count": 1,
        }
    )

    # Insert a flagged video in violateVideos
    import sqlite3

    conn = sqlite3.connect(db_file)
    conn.execute(
        """
        INSERT INTO violateVideos (profile_id, video_id, title, violate_title, violate_description, status)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            profile_id,
            "72983719827391",
            "Creative Reel #1",
            "Gậy Nguyên Tác (Unoriginal Content)",
            "Nội dung không đủ tính nguyên bản để nhận thưởng FYP",
            "pending",
        ),
    )
    conn.commit()
    conn.close()

    return {
        "db_file": db_file,
        "prof_repo": prof_repo,
        "proxy_repo": proxy_repo,
        "profile_id": profile_id,
        "proxy_id": proxy_id,
    }


def test_gologin_tiktok_client_resolves_cookies_and_proxy(isolated_env):
    """Verifies GoLoginTikTokClient extracts decrypted DPAPI cookies and proxies from DB."""
    from src.infrastructure.tiktok.gologin_tiktok_client import GoLoginTikTokClient

    client = GoLoginTikTokClient(db_path=isolated_env["db_file"])
    p_id = isolated_env["profile_id"]

    cookie_hdr = client.get_profile_cookie_header(p_id)
    assert "sessionid=test_session_token_xyz" in cookie_hdr
    assert "passport_csrf_token=csrf_123" in cookie_hdr

    proxy_dict = client.get_profile_proxy(p_id)
    assert proxy_dict is not None
    assert proxy_dict["host"] == "118.70.171.85"
    assert proxy_dict["port"] == 46796


def test_submit_video_appeal_success(isolated_env):
    """Verifies that submitting a video appeal updates violateVideos and inserts accountAppeals."""
    from src.infrastructure.tiktok.moderation_service import TikTokModerationService

    service = TikTokModerationService(db_path=isolated_env["db_file"])
    p_id = isolated_env["profile_id"]
    video_id = "72983719827391"
    reason = "Video do chính chủ sản xuất, tuân thủ 100% chính sách nguyên tác của TikTok."

    res = service.submit_video_appeal(
        profile_id=p_id,
        video_id=video_id,
        appeal_reason=reason,
        mock_success=True,
    )
    assert res["ok"] is True
    assert res["status"] == "appealed"
    assert res["video_id"] == video_id

    # Verify violateVideos table mutation
    import sqlite3

    conn = sqlite3.connect(isolated_env["db_file"])
    conn.row_factory = sqlite3.Row
    v_row = conn.execute(
        "SELECT status, appeal_date FROM violateVideos WHERE profile_id=? AND video_id=?",
        (p_id, video_id),
    ).fetchone()
    assert v_row is not None
    assert v_row["status"] == "appealed"
    assert v_row["appeal_date"] is not None

    # Verify accountAppeals table mutation
    a_row = conn.execute(
        "SELECT * FROM accountAppeals WHERE profile_id=? AND object_id=?",
        (p_id, video_id),
    ).fetchone()
    assert a_row is not None
    assert a_row["appeal_type"] == "video_strike"
    assert a_row["reason"] == reason
    conn.close()


def test_reapply_creator_rewards_countdown_blocked(isolated_env):
    """Verifies that re-applying before penalty expiry is blocked with days_left countdown."""
    from src.infrastructure.tiktok.moderation_service import TikTokModerationService

    service = TikTokModerationService(db_path=isolated_env["db_file"])
    p_id = isolated_env["profile_id"]

    # Set date_reapply to 10 days in future
    future_date = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
    import sqlite3

    conn = sqlite3.connect(isolated_env["db_file"])
    conn.execute("UPDATE profiles SET date_reapply=? WHERE id=?", (future_date, p_id))
    conn.commit()
    conn.close()

    res = service.submit_creator_rewards_reapply(p_id)
    assert res["ok"] is False
    assert res["days_left"] == 10
    assert "chưa đến hạn" in res["error"].lower() or "not arrived" in res["error"].lower()


def test_reapply_creator_rewards_success(isolated_env):
    """Verifies that re-applying when eligible restores account_standing to Good and clears date_reapply."""
    from src.infrastructure.tiktok.moderation_service import TikTokModerationService

    service = TikTokModerationService(db_path=isolated_env["db_file"])
    p_id = isolated_env["profile_id"]

    # Set date_reapply to past date
    past_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
    import sqlite3

    conn = sqlite3.connect(isolated_env["db_file"])
    conn.execute("UPDATE profiles SET date_reapply=?, account_standing='Warning' WHERE id=?", (past_date, p_id))
    conn.commit()
    conn.close()

    res = service.submit_creator_rewards_reapply(p_id, mock_success=True)
    assert res["ok"] is True
    assert res["status"] == "submitted"

    # Verify profile updated
    conn = sqlite3.connect(isolated_env["db_file"])
    conn.row_factory = sqlite3.Row
    p_row = conn.execute("SELECT account_standing, date_reapply FROM profiles WHERE id=?", (p_id,)).fetchone()
    assert p_row["account_standing"] == "Good"
    assert p_row["date_reapply"] is None
    conn.close()


def test_account_health_dialog_renders_appeal_actions_and_reapply(isolated_env, app_instance):
    """Verifies AccountHealthDialog contains Creator Rewards reapply card, appeal button, and check appeals button."""
    from src.presentation.dialogs.account_health_dialog import AccountHealthDialog

    p_id = isolated_env["profile_id"]
    dialog = AccountHealthDialog(profile_id=p_id, db_path=isolated_env["db_file"])

    assert hasattr(dialog, "btn_appeal_video")
    assert hasattr(dialog, "btn_check_appeals")
    assert hasattr(dialog, "btn_reapply_creator")
    assert hasattr(dialog, "card_reapply_countdown")

    assert dialog.table_violate.rowCount() == 1
    dialog.table_violate.selectRow(0)

    # Trigger submit appeal
    with patch.object(
        dialog.moderation_service, "submit_video_appeal", return_value={"ok": True, "status": "appealed"}
    ):
        dialog._on_appeal_selected_video(mock_reason="Bản quyền chính chủ")
        assert dialog.table_violate.item(0, 4).text() == "Đã nộp kháng cáo"

    dialog.close()
    dialog.deleteLater()
    app_instance.processEvents()
