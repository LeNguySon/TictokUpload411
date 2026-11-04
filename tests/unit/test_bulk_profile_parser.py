"""
Unit tests for Bulk Profile Parser.
Strict TDD - Phase 2 (RED)
"""

from src.presentation.dialogs.bulk_add_profile_dialog import parse_bulk_profile_line


def test_parse_bulk_profile_line_pipe_delimited():
    line = "TikTok_US_01|103.20.5.10:8080:u1:p1|msToken=abc12345; sessionid=xyz|mike@domain.com|Campaign 1"
    parsed = parse_bulk_profile_line(line)
    assert parsed is not None
    assert parsed["name"] == "TikTok_US_01"
    assert parsed["proxy_raw"] == "103.20.5.10:8080:u1:p1"
    assert "msToken=abc12345" in parsed["cookie"]
    assert parsed["email"] == "mike@domain.com"
    assert parsed["note"] == "Campaign 1"


def test_parse_bulk_profile_line_minimal():
    # Only name and cookie
    line = "Acc_Simple|msToken=just_a_cookie"
    parsed = parse_bulk_profile_line(line)
    assert parsed is not None
    assert parsed["name"] == "Acc_Simple"
    assert parsed["cookie"] == "msToken=just_a_cookie"
    assert parsed["proxy_raw"] is None


def test_parse_bulk_profile_line_raw_cookie_only():
    # Auto-generate name from timestamp or sequence if only cookie provided
    line = "sessionid=998877665544; msToken=tok123"
    parsed = parse_bulk_profile_line(line, default_name_prefix="Profile_Auto")
    assert parsed is not None
    assert "Profile_Auto" in parsed["name"]
    assert "sessionid=998877665544" in parsed["cookie"]


def test_parse_bulk_profile_line_empty():
    assert parse_bulk_profile_line("") is None
    assert parse_bulk_profile_line("   ") is None
