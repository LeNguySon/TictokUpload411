"""TikTok analytics return hours in the ``tz_offset`` / ``time_offset`` the request sends (live 2026-11-07, profile
78: +7h -> peak 06:00, 0 -> 00:00, -6h -> 17:00). The app schedules on the machine's clock, so the requests must
send the machine's own UTC offset: it was hard-coded to 25200 (UTC+7), wrong on any machine outside UTC+7."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from src.infrastructure.tiktok import request_time


def test_offset_follows_the_machine_clock():
    mexico = datetime(2026, 11, 7, 12, 0, tzinfo=timezone(timedelta(hours=-6)))
    with patch.object(request_time, "_local_now", return_value=mexico):
        assert request_time.local_utc_offset_seconds() == -21600
    vietnam = datetime(2026, 11, 7, 12, 0, tzinfo=timezone(timedelta(hours=7)))
    with patch.object(request_time, "_local_now", return_value=vietnam):
        assert request_time.local_utc_offset_seconds() == 25200


def test_real_machine_offset_matches_python():
    expected = int(datetime.now().astimezone().utcoffset().total_seconds())
    assert request_time.local_utc_offset_seconds() == expected


def _offsets(urls):
    found = set()
    for url in urls:
        found.update(int(v) for v in re.findall(r"(?:tz_offset|time_offset)=(-?\d+)", url))
    return found


@pytest.fixture
def mexico_clock():
    with patch.object(request_time, "local_utc_offset_seconds", return_value=-21600):
        yield


def test_client_analytics_requests_send_the_machine_offset(tmp_path: Path, mexico_clock):
    from src.infrastructure.tiktok.gologin_tiktok_client import GoLoginTikTokClient

    client = GoLoginTikTokClient(db_path=tmp_path / "app.db")
    urls: list[str] = []
    with patch.object(client, "request_api", side_effect=lambda pid, url, **kw: urls.append(url) or {}):
        client.fetch_audience_intelligence(1)
        client.fetch_video_deep_analytics(1, "123")
    assert urls and _offsets(urls) == {-21600}


def test_deep_sync_insight_requests_send_the_machine_offset(tmp_path: Path, mexico_clock):
    from src.infrastructure.database.migrations.runner import run_all_migrations
    from src.infrastructure.database.repositories.profile_repository import ProfileRepository
    from src.infrastructure.tiktok.passive_sync_service import PassiveTikTokSyncService

    db = tmp_path / "app.db"
    run_all_migrations(db)
    repo = ProfileRepository(db)
    pid = repo.create({"name": "ch", "cookies_json": "sessionid=x", "direct_connection": 1})
    svc = PassiveTikTokSyncService(repo, db_path=db)
    urls: list[str] = []
    with patch.object(svc.client, "get_profile_cookie_header", return_value="sessionid=x"), \
            patch.object(svc.client, "request_api", side_effect=lambda pid, url, **kw: urls.append(url) or {}), \
            patch("src.infrastructure.tiktok.passive_sync_service.download_and_cache_avatar"), \
            patch("src.infrastructure.tiktok.moderation_service.TikTokModerationService.fetch_video_violations",
                  return_value=[]):
        svc.sync_profile_deep_creator_api(pid)
    insight_urls = [u for u in urls if "offset=" in u]
    assert insight_urls and _offsets(insight_urls) == {-21600}


def test_no_hardcoded_offset_left_in_the_sources():
    root = Path(__file__).resolve().parents[2] / "src"
    offenders = [
        str(p.relative_to(root))
        for p in root.rglob("*.py")
        if re.search(r"(?:tz_offset|time_offset)=\d", p.read_text(encoding="utf-8"))
    ]
    assert offenders == []
