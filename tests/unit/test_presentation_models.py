"""
Unit tests for Presentation Table Models and Formatting Helpers.
Strict TDD - Phase 2 (RED)
"""

from src.presentation.widgets.table_helpers import (
    format_duration_string,
    format_mmo_metric,
    format_money_string,
    get_profile_table_headers,
    get_video_table_headers,
)


def test_table_headers_match_specification():
    profile_headers = get_profile_table_headers()
    assert len(profile_headers) == 29
    assert profile_headers[0] == "STT"
    assert profile_headers[1] == "Avt"
    assert profile_headers[2] == "Tên hồ sơ"
    assert profile_headers[3] == "Logged"
    assert profile_headers[4] == "Proxy"
    assert profile_headers[12] == "Tình trạng"
    assert profile_headers[14] == "$Earned"
    assert profile_headers[18] == "QG"
    assert profile_headers[28] == "ID"

    video_headers = get_video_table_headers()
    assert len(video_headers) == 16  # 16 columns since b6eb013 (Source -> Tiến trình + Nhật Ký Upload)
    assert video_headers[0] == "STT"
    assert video_headers[1] == "Tiêu đề"
    assert video_headers[2] == "Dự Án"
    assert video_headers[5] == "Duration"
    assert video_headers[6] == "Hiển thị"
    assert video_headers[8] == "Upload To"
    assert video_headers[9] == "Tình trạng"
    assert video_headers[10] == "Tiến trình"


def test_formatting_helpers():
    # Metric formatting
    assert format_mmo_metric(0) == "0"
    assert format_mmo_metric(1163) == "1,163"
    assert format_mmo_metric(2128959) == "2,128,959"

    # Duration formatting
    assert format_duration_string(7.0) == "00:00:07"
    assert format_duration_string(65.0) == "00:01:05"
    assert format_duration_string(3605.0) == "01:00:05"

    # Money formatting
    assert format_money_string(0.0) == "$0.00"
    assert format_money_string(1250.5) == "$1,250.50"
    assert format_money_string(0.45) == "$0.45"
