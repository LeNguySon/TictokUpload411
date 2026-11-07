"""
Unit tests for TikTok Creator Studio Deep Analytics Service & Parsing.
Follows Strict TDD (Red -> Green -> Refactor) under ECC Development Lifecycle.
"""

from pathlib import Path

from src.infrastructure.database.connection import db_session
from src.infrastructure.database.migrations.runner import run_all_migrations


def test_migrations_create_deep_analytics_columns_and_table(tmp_path: Path):
    """Verifies runner.py creates all new analytics columns on profiles, videoTables, and creates video_deep_analytics."""
    db_file = tmp_path / "test_mig.db"
    run_all_migrations(db_file)

    with db_session(db_file) as conn:
        prof_cols = [r[1] for r in conn.execute("PRAGMA table_info(profiles)").fetchall()]
        assert "audience_demographics_json" in prof_cols
        assert "optimal_posting_hours_json" in prof_cols
        assert "competitor_intelligence_json" in prof_cols
        assert "publish_settings_json" in prof_cols

        vt_cols = [r[1] for r in conn.execute("PRAGMA table_info(videoTables)").fetchall()]
        assert "search_terms_json" in vt_cols
        assert "traffic_sources_json" in vt_cols
        assert "retention_points_json" in vt_cols
        assert "finish_rate" in vt_cols
        assert "viewer_locations_json" in vt_cols
        assert "ai_comments_json" in vt_cols

        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        assert "video_deep_analytics" in tables


def test_calculate_optimal_post_hours_peak_detection():
    """Verifies optimal posting hour algorithm accurately identifies the peak follower window."""
    from src.infrastructure.tiktok.deep_analytics_parser import calculate_optimal_post_hours

    # 7 days x 24 hours sample matrix with peak at hour 8 (08:00)
    matrix = []
    for _day in range(7):
        hours_arr = [1000] * 24
        hours_arr[7] = 4200
        hours_arr[8] = 4800  # Peak
        hours_arr[9] = 4300
        matrix.append({"status": 0, "value": hours_arr})

    res = calculate_optimal_post_hours(matrix)
    assert res["peak_hour"] == 8
    assert res["peak_window"] == "07:00 - 09:00"
    assert res["peak_users"] >= 4500
    assert "hourly_totals" in res
    assert len(res["hourly_totals"]) == 24


def test_calculate_optimal_post_hours_fallback_on_empty():
    """Verifies graceful fallback to noon (12:00) when data is missing or empty."""
    from src.infrastructure.tiktok.deep_analytics_parser import calculate_optimal_post_hours

    res_empty = calculate_optimal_post_hours([])
    assert res_empty["peak_hour"] == 12
    assert res_empty["peak_window"] == "12:00 - 14:00"
    assert res_empty["peak_users"] == 0

    res_none = calculate_optimal_post_hours(None)
    assert res_none["peak_hour"] == 12


def test_parse_search_terms_and_seo():
    """Verifies item search terms are cleanly parsed into structured keywords and percentages."""
    from src.infrastructure.tiktok.deep_analytics_parser import parse_search_terms

    raw = {
        "status": 0,
        "value": [
            {"key": "riya en español", "str_value": "0.15", "value": 0.15},
            {"key": "riya", "str_value": "0.147", "value": 0.147},
            {"key": "sara dormitorio parte 2", "str_value": "0.048", "value": 0.048},
        ]
    }

    terms = parse_search_terms(raw)
    assert len(terms) == 3
    assert terms[0]["keyword"] == "riya en español"
    assert terms[0]["percentage"] == 15.0
    assert terms[1]["keyword"] == "riya"
    assert terms[1]["percentage"] == 14.7


def test_parse_retention_curve_and_finish_rate():
    """Verifies second-by-second drop-off points and finish rate are extracted."""
    from src.infrastructure.tiktok.deep_analytics_parser import parse_retention_data

    raw_retention = {
        "status": 0,
        "value": {
            "list": [
                {"timestamp": "0", "value": 1.0},
                {"timestamp": "1000", "value": 0.89},
                {"timestamp": "2000", "value": 0.79},
            ]
        }
    }
    raw_finish = {"status": 0, "value": 0.1334}

    res = parse_retention_data(raw_retention, raw_finish)
    assert res["finish_rate"] == 13.34
    assert len(res["points"]) == 3
    assert res["points"][0] == {"second": 0, "retention": 100.0}
    assert res["points"][1] == {"second": 1, "retention": 89.0}
    assert res["points"][2] == {"second": 2, "retention": 79.0}


def test_parse_peer_competitor_intelligence():
    """Verifies competitor creators and competitor videos are cleanly structured."""
    from src.infrastructure.tiktok.deep_analytics_parser import parse_competitor_intelligence

    raw_users = {
        "status": 0,
        "value": [
            {
                "nickname": "Carlos Fuentes",
                "unique_id": "carlhoos_",
                "follower_count": 22773135,
                "avatar_thumb": {"url_list": ["https://example.com/avatar.jpg"]}
            }
        ]
    }
    raw_items = {
        "status": 0,
        "value": [
            {
                "aweme_id": "7704068589417991444",
                "desc": "cuando se le pegaba el slime",
                "statistics": {"play_count": 594962, "digg_count": 62848},
                "video": {"play_addr": {"url_list": ["https://example.com/video.mp4"]}}
            }
        ]
    }

    ci = parse_competitor_intelligence(raw_users, raw_items)
    assert len(ci["top_creators"]) == 1
    assert ci["top_creators"][0]["unique_id"] == "carlhoos_"
    assert ci["top_creators"][0]["follower_count"] == 22773135
    assert len(ci["top_videos"]) == 1
    assert ci["top_videos"][0]["aweme_id"] == "7704068589417991444"
    assert ci["top_videos"][0]["play_count"] == 594962
    assert ci["top_videos"][0]["download_url"] == "https://example.com/video.mp4"

def test_client_fetch_publish_settings(tmp_path: Path):
    """Verifies fetch_publish_settings correctly queries publish setting endpoint."""
    from unittest.mock import MagicMock

    from src.infrastructure.tiktok.gologin_tiktok_client import GoLoginTikTokClient

    client = GoLoginTikTokClient(db_path=tmp_path / "app.db")
    client.request_api = MagicMock(return_value={
        "_status_code": 200,
        "enable_auto_music_copyright_check": True,
        "enable_auto_post_check": True,
        "disable_tto_plus_showcase": False,
    })

    res = client.fetch_publish_settings(profile_id=1)
    assert res["enable_auto_music_copyright_check"] is True
    assert res["enable_auto_post_check"] is True
    assert res["disable_tto_plus_showcase"] is False
    assert res["status_code"] == 200


def test_client_fetch_audience_intelligence(tmp_path: Path):
    """Verifies fetch_audience_intelligence aggregates demographics, active hours, and competitor spy."""
    from unittest.mock import MagicMock

    from src.infrastructure.tiktok.gologin_tiktok_client import GoLoginTikTokClient

    client = GoLoginTikTokClient(db_path=tmp_path / "app.db")

    def mock_request(pid, url, **kwargs):
        if "analytics/insights" in url:
            return {
                "_status_code": 200,
                "analytics_follower_country_city_percent": {
                    "key_value": [{"country_name": "US", "country_percent": 0.5, "key_value": []}]
                },
                "analytics_viewer_total_viewer": {"total": {"value": 150000}}
            }
        elif "aweme/v2/data/insight" in url:
            return {
                "_status_code": 200,
                "follower_active_history_hours": [{"value": [100] * 24}],
                "viewer_also_watched_users": {"value": [{"unique_id": "rival_creator"}]}
            }
        return {}

    client.request_api = MagicMock(side_effect=mock_request)
    intel = client.fetch_audience_intelligence(profile_id=1)

    assert "demographics" in intel
    assert intel["demographics"]["viewer_total_7d"] == 150000
    assert "optimal_hours" in intel
    assert "competitor_intelligence" in intel
    assert intel["competitor_intelligence"]["top_creators"][0]["unique_id"] == "rival_creator"
