"""Fixes from the review of 63877e2 (creator-studio deep telemetry).

1. The "best posting hour" must come from MEASURED audience activity only. ``profiles.optimal_hour`` has a schema
   default of 12 and the parser returns a 12:00 placeholder without data, so every channel showed "12:00".
2. The Credential Vault must not silently skip storage when keyring cannot be imported.
3. The schedule dialog accepts a measured window without an hour (type-safe).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from src.domain.analytics.optimal_hours import measured_optimal_schedule
from src.infrastructure.database.connection import get_db_connection
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.tiktok.deep_analytics_parser import calculate_optimal_post_hours

MEASURED = {"peak_hour": 6, "peak_window": "05:00 - 07:00", "peak_users": 4429, "hourly_totals": [1] * 24}


@pytest.mark.parametrize(
    "profile",
    [
        {"optimal_hour": 12},  # schema default, nothing measured
        {"optimal_hour": 12, "optimal_posting_hours_json": json.dumps(calculate_optimal_post_hours([]))},
        {"optimal_posting_hours_json": "not json"},
        {"optimal_posting_hours_json": json.dumps({"peak_hour": 30, "peak_users": 10})},
        {},
    ],
)
def test_unmeasured_profiles_have_no_optimal_schedule(profile):
    assert measured_optimal_schedule(profile) is None


def test_measured_profile_gives_hour_window_and_users():
    m = measured_optimal_schedule({"optimal_hour": 12, "optimal_posting_hours_json": json.dumps(MEASURED)})
    assert m is not None
    assert (m.hour, m.window, m.peak_users) == (6, "05:00 - 07:00", 4429)


def test_measured_schedule_accepts_already_decoded_json():
    m = measured_optimal_schedule({"optimal_posting_hours_json": {"peak_hour": 22, "peak_users": 5}})
    assert m is not None and m.hour == 22 and m.window == "21:00 - 23:00"


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "app.db"
    run_all_migrations(path)
    return path


def _deep_sync(db: Path, intel: dict) -> dict:
    from src.infrastructure.tiktok.passive_sync_service import PassiveTikTokSyncService

    repo = ProfileRepository(db)
    pid = repo.create(name="ch", project_id=1, cookies_json='[{"name": "sessionid", "value": "x"}]')
    svc = PassiveTikTokSyncService(profile_repo=repo, db_path=db)
    with patch.object(svc.client, "get_profile_cookie_header", return_value="sessionid=x"), patch.object(
        svc.client, "request_api", return_value={}
    ), patch.object(svc.client, "fetch_audience_intelligence", return_value=intel), patch.object(
        svc.client, "fetch_publish_settings", return_value={}
    ), patch("src.infrastructure.tiktok.passive_sync_service.download_and_cache_avatar"):
        svc.sync_profile_deep_creator_api(pid)
    row = repo.get_by_id(pid)
    assert row is not None
    return row


def test_deep_sync_does_not_store_placeholder_posting_hours(db):
    row = _deep_sync(db, {"optimal_hours": calculate_optimal_post_hours([])})
    assert row["optimal_posting_hours_json"] is None
    assert measured_optimal_schedule(row) is None


def test_deep_sync_stores_measured_posting_hours(db):
    row = _deep_sync(db, {"optimal_hours": MEASURED})
    assert row["optimal_hour"] == 6
    assert measured_optimal_schedule(row) is not None


def test_sniffer_active_hours_are_stored_as_measured_schedule(db):
    from src.infrastructure.tiktok.network_sniffer import TikTokNetworkSniffer

    pid = ProfileRepository(db).create(name="ch", project_id=1)
    hourly = [{"key": str(h), "value": 1000 + (15000 if h == 22 else h * 100)} for h in range(24)]
    TikTokNetworkSniffer(db_path=db).process_api_response(
        pid,
        "https://www.tiktok.com/tiktok/v1/analytics/insights/",
        {"analytics_viewer_active_hours": {"list": [{"key": "20261029", "list": {"key_value": hourly}}]}},
    )
    conn = get_db_connection(db)
    row = dict(conn.execute("SELECT * FROM profiles WHERE id=?", (pid,)).fetchone())
    conn.close()
    m = measured_optimal_schedule(row)
    assert m is not None and m.hour == 22 and m.peak_users == 16000


def test_radar_ignores_the_default_optimal_hour(db, qtbot):
    from src.presentation.dialogs.channel_radar_dialog import ChannelRadarDialog

    repo = ProfileRepository(db)
    pid = repo.create(name="ch", project_id=1)
    assert repo.get_by_id(pid)["optimal_hour"] == 12  # schema default
    conn = get_db_connection(db)
    for i, hour in enumerate((20, 20, 20)):  # the channel's own videos peak at 20:00
        conn.execute(
            "INSERT INTO statisticTable (profile_id, id_video, views, likes, comments, shares, date_upload)"
            " VALUES (?, ?, ?, 10, 1, 1, ?);",
            (pid, f"v{i}", 1000 + i, f"2026-11-0{i + 1} {hour}:15:00"),
        )
    conn.commit()
    conn.close()
    dlg = ChannelRadarDialog(profile_id=pid, profile_repo=repo, db_path=db)
    qtbot.addWidget(dlg)
    assert "12:00" not in dlg.lbl_optimal_hour_stat.text()
    assert "20:00" in dlg.lbl_optimal_hour_stat.text()


def test_schedule_dialog_with_measured_window_only(qtbot):
    from src.presentation.dialogs.schedule_dialog import ScheduleVideoDialog

    dlg = ScheduleVideoDialog(video_count=2, optimal_window="05:00 - 07:00")
    qtbot.addWidget(dlg)
    dlg._set_to_next_optimal_hour()
    assert dlg.dt_start.dateTime().toPyDateTime().hour == 5


def test_vault_requires_keyring():
    import keyring
    from src.infrastructure.credentials import windows_vault

    assert windows_vault.keyring is keyring


def test_radar_escapes_competitor_titles_from_tiktok(db, qtbot):
    from PyQt6.QtWidgets import QLabel
    from src.presentation.dialogs.channel_radar_dialog import ChannelRadarDialog

    repo = ProfileRepository(db)
    pid = repo.create(name="ch", project_id=1)
    intel = {
        "top_creators": [{"unique_id": "a<i>b", "follower_count": "1200"}],
        "top_videos": [{"desc": "<b>bold</b> & co", "play_count": "5000"}],
    }
    repo.update(pid, competitor_intelligence_json=json.dumps(intel))
    dlg = ChannelRadarDialog(profile_id=pid, profile_repo=repo, db_path=db)
    qtbot.addWidget(dlg)
    texts = [lbl.text() for lbl in dlg.findChildren(QLabel)]
    videos = next(t for t in texts if "Video viral" in t)
    creators = next(t for t in texts if "Kênh đối thủ" in t)
    assert "&lt;b&gt;bold&lt;/b&gt; &amp; co" in videos and "5,000 views" in videos
    assert "@a&lt;i&gt;b" in creators and "1,200 flw" in creators
