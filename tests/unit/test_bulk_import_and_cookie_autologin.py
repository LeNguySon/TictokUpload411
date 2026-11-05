"""
Unit tests for bulk profile import with flexible format customization and browser cookie auto-login injection.
"""

from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_profile_import_parser_8_fields_mmo_preset():
    from src.application.parsers.profile_import_parser import ProfileImportParser

    line = "user_mmo1|pass_tt123|sessionid=abc12345; msToken=tok999|user1@gmail.com|pass_mail456|rt_oauth_xyz|cid_app_789|mail_ck=m123"
    parsed = ProfileImportParser.parse_line(line, format_name="mmo_8_fields")

    assert parsed is not None
    assert parsed["user"] == "user_mmo1"
    assert parsed["pass"] == "pass_tt123"
    assert "sessionid=abc12345" in parsed["cookie"]
    assert parsed["email"] == "user1@gmail.com"
    assert parsed["pass_mail"] == "pass_mail456"
    assert parsed["refresh_token"] == "rt_oauth_xyz"
    assert parsed["client_id"] == "cid_app_789"
    assert parsed["cookie_email"] == "mail_ck=m123"


def test_profile_import_parser_custom_order_and_delimiter():
    from src.application.parsers.profile_import_parser import ProfileImportParser

    # Custom order: Email : Passmail : User : Pass : Cookie
    custom_format = "Email:Passmail:User:Pass:Cookie"
    line = "creator@tiktok.com:emailpass999:tt_creator:tiktokpass123:sessionid=sess_valid_888"

    parsed = ProfileImportParser.parse_line(line, custom_template=custom_format, delimiter=":")
    assert parsed is not None
    assert parsed["email"] == "creator@tiktok.com"
    assert parsed["pass_mail"] == "emailpass999"
    assert parsed["user"] == "tt_creator"
    assert parsed["pass"] == "tiktokpass123"
    assert parsed["cookie"] == "sessionid=sess_valid_888"


def test_profile_import_parser_raw_cookie_fallback():
    from src.application.parsers.profile_import_parser import ProfileImportParser

    line = "msToken=token_only_123; sessionid=sess_only_456; ttwid=wid789"
    parsed = ProfileImportParser.parse_line(line)
    assert parsed is not None
    assert "sessionid=sess_only_456" in parsed["cookie"]
    assert parsed["user"].startswith("Profile_") or parsed["user"].startswith("TikTok_")


def test_browser_cookie_injector_parse_cookie_string_to_dicts():
    from src.infrastructure.browser.cookie_injector import BrowserCookieInjector

    cookie_str = "sessionid=9f8a7b6c5d4e; msToken=xyz123; ttwid=tt_wid_val"
    cookie_items = BrowserCookieInjector.parse_cookie_string(cookie_str, domain=".tiktok.com")

    assert len(cookie_items) == 3
    names = {c["name"]: c for c in cookie_items}

    assert "sessionid" in names
    assert names["sessionid"]["value"] == "9f8a7b6c5d4e"
    assert names["sessionid"]["domain"] == ".tiktok.com"
    assert names["sessionid"]["httpOnly"] is True
    assert names["sessionid"]["secure"] is True

    assert "msToken" in names
    assert names["msToken"]["value"] == "xyz123"


def test_browser_cookie_injector_injects_into_gologin_sdk():
    from src.infrastructure.browser.cookie_injector import BrowserCookieInjector

    mock_gl = MagicMock()
    mock_gl.post_cookies.return_value = True

    cookie_str = "sessionid=sess_success_123; msToken=tok_success_456"
    success = BrowserCookieInjector.inject_to_gologin(
        profile_uuid="uuid-mock-123",
        cookie_raw=cookie_str,
        gl_instance=mock_gl,
    )

    assert success is True
    assert mock_gl.post_cookies.called
    called_args = mock_gl.post_cookies.call_args[0][0]
    assert isinstance(called_args, list)
    assert len(called_args) == 2
    assert any(c["name"] == "sessionid" and c["value"] == "sess_success_123" for c in called_args)


def test_bulk_add_profile_dialog_agentshield_masking_and_preview(qapp):
    from src.presentation.dialogs.bulk_add_profile_dialog import BulkAddProfileDialog

    mock_profile_repo = MagicMock(spec=ProfileRepository)
    mock_project_repo = MagicMock(spec=ProjectRepository)
    mock_proxy_repo = MagicMock(spec=ProxyRepository)
    mock_project_repo.list_all.return_value = [{"id": 1, "name": "Dự án MMO"}]

    dlg = BulkAddProfileDialog(
        profile_repo=mock_profile_repo,
        project_repo=mock_project_repo,
        proxy_repo=mock_proxy_repo,
    )

    # Input line with sensitive pass and cookie
    dlg.txt_input.setPlainText("user_test|secret_password_123|sessionid=sensitive_cookie_999|test@mail.com|mail_secret")
    dlg._on_preview()

    # Table preview should show 1 row
    assert dlg.table_preview.rowCount() == 1

    # Check password masking
    pass_item = dlg.table_preview.item(0, 2)  # Col 2 is Password
    assert pass_item is not None
    assert pass_item.text() == "••••••••"

    # Check cookie masking
    cookie_item = dlg.table_preview.item(0, 3)  # Col 3 is Cookie
    assert cookie_item is not None
    assert "sensitive_cookie_999" not in cookie_item.text()
    assert "***" in cookie_item.text() or "..." in cookie_item.text()


def test_bulk_add_profile_dialog_import_all_execution(qapp, tmp_path):
    from src.presentation.dialogs.bulk_add_profile_dialog import BulkAddProfileDialog

    test_db = tmp_path / "test_bulk_import.db"
    from src.infrastructure.database.migrations.runner import run_all_migrations

    run_all_migrations(test_db)

    profile_repo = ProfileRepository(db_path=test_db)
    project_repo = ProjectRepository(db_path=test_db)
    proxy_repo = ProxyRepository(db_path=test_db)

    dlg = BulkAddProfileDialog(
        profile_repo=profile_repo,
        project_repo=project_repo,
        proxy_repo=proxy_repo,
    )

    test_line = "creator_pro|mypassword999|sessionid=valid_sess_111; msToken=tok222|creator@tiktok.com|mailpass333|rf_token_444|cid_555|mailck_666"
    dlg.txt_input.setPlainText(test_line)

    with patch(
        "src.infrastructure.browser.cookie_injector.BrowserCookieInjector.inject_to_gologin", return_value=True
    ) as mock_inject:
        dlg._on_import_all()

    # Verify profile created in DB
    profiles = profile_repo.list_all()
    assert len(profiles) >= 1
    imported = profiles[0]

    assert imported["name"] == "creator_pro"
    assert imported["password"] == "mypassword999"
    assert "sessionid=valid_sess_111" in imported["cookies_json"]
    assert imported["email"] == "creator@tiktok.com"
    assert imported["email_backup_password"] == "mailpass333"
    assert imported["refresh_token"] == "rf_token_444"
    assert imported["client_id"] == "cid_555"
    assert imported["cookie_email"] == "mailck_666"
    assert imported["status"] == "LIVE"
    assert mock_inject.called
