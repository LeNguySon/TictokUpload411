"""
Follow-ups from the live test on @swall.pain (2026-11-07):
1. Violation scan took 85 s for 79 videos: one getPenaltyDetails request per video, strictly sequential, and only
   the first item_list page (50 of 79 videos) was ever checked.
2. The appeal deadline column showed a raw epoch ("1788811033").
3. The radar's best posting hour was always 12: no video carried its real posting hour.
4. Avatars were never downloaded for a profile that runs from the machine's IP (direct_connection=1).
"""

from __future__ import annotations

import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository

ITEM_LIST = "item_list/v1"
PENALTY = "getPenaltyDetails"


@pytest.fixture
def env(tmp_path: Path) -> dict:
    db = tmp_path / "followups.db"
    run_all_migrations(db)
    profiles = ProfileRepository(db)
    pid = profiles.create(
        {
            "name": "swall-like",
            "status": "LIVE",
            "cookies_json": '[{"name": "sessionid", "value": "fake_sess"}]',
            "storage_dir": str(tmp_path / "profiles" / "p"),
        }
    )
    return {"db": db, "profiles": profiles, "proxies": ProxyRepository(db), "pid": pid, "tmp": tmp_path}


def _item(n: int) -> dict:
    return {"item_id": f"76{n:017d}", "desc": f"clip {n}", "create_time": "1788223580"}


# ---------------------------------------------------------------- 1. violation scan


def _fake_api(pages: list[list[dict]], penalized: set[str], delay: float = 0.0, stats: dict | None = None):
    lock = threading.Lock()
    state = {"active": 0, "peak": 0, "penalty_calls": 0}

    def request(url, cookie, ua, profile_id=None, method="GET", json_data=None, timeout=15, **_):
        if ITEM_LIST in url:
            cursor = int((json_data or {}).get("cursor") or 0)
            page = pages[cursor]
            more = cursor + 1 < len(pages)
            return {"status_code": 0, "item_list": page, "has_more": more, "cursor": cursor + 1 if more else cursor}
        if PENALTY in url:
            with lock:
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])
                state["penalty_calls"] += 1
            time.sleep(delay)
            with lock:
                state["active"] -= 1
            vid = url.rsplit("=", 1)[-1]
            if vid in penalized:
                return {"penalties": [{"date": "1788811033", "penalty_reason_info_list": [{"title": "CG"}]}],
                        "appeal_status": 0}
            return {"penalties": [], "appeal_status": 2}
        return {}

    if stats is not None:
        stats.update(state)
    return request, state


def test_violation_scan_reads_every_item_list_page(env) -> None:
    from src.infrastructure.tiktok.moderation_service import TikTokModerationService

    pages = [[_item(i) for i in range(50)], [_item(i) for i in range(50, 79)]]
    late_video = _item(70)["item_id"]
    request, state = _fake_api(pages, penalized={late_video})
    svc = TikTokModerationService(db_path=env["db"])
    with patch.object(svc, "_request_tiktok_api", side_effect=request):
        violations = svc.fetch_video_violations(env["pid"])

    assert state["penalty_calls"] == 79
    assert [v["video_id"] for v in violations] == [late_video]


def test_violation_scan_checks_penalties_concurrently_and_bounded(env) -> None:
    from src.infrastructure.tiktok import moderation_service as mod

    pages = [[_item(i) for i in range(24)]]
    request, state = _fake_api(pages, penalized={_item(3)["item_id"], _item(17)["item_id"]}, delay=0.05)
    svc = mod.TikTokModerationService(db_path=env["db"])
    with patch.object(svc, "_request_tiktok_api", side_effect=request):
        violations = svc.fetch_video_violations(env["pid"])

    assert 1 < state["peak"] <= mod.PENALTY_LOOKUP_WORKERS
    assert [v["video_id"] for v in violations] == [_item(3)["item_id"], _item(17)["item_id"]]  # item order kept


# ---------------------------------------------------------------- 2. appeal deadline display


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1788811033", datetime.fromtimestamp(1788811033).strftime("%d/%m/%Y")),
        ("1788811033000", datetime.fromtimestamp(1788811033).strftime("%d/%m/%Y")),  # milliseconds
        ("2026-11-20", "20/11/2026"),
        ("2026-11-07 01:02:31", "07/11/2026"),
        ("", "—"),
        (None, "—"),
        ("soon", "soon"),
    ],
)
def test_format_appeal_deadline(raw, expected) -> None:
    from src.presentation.dialogs.account_health_dialog import format_appeal_deadline

    assert format_appeal_deadline(raw) == expected


# ---------------------------------------------------------------- 3. radar posting hour


def test_sniffer_stores_video_upload_time(env) -> None:
    from src.infrastructure.tiktok.network_sniffer import TikTokNetworkSniffer

    posted = 1788223580
    item = {"item_id": "7600000000000000099", "create_time": str(posted), "play_count": "10"}
    TikTokNetworkSniffer(db_path=env["db"])._upsert_video_items(env["pid"], [item])

    con = sqlite3.connect(env["db"])
    (date_upload,) = con.execute("SELECT date_upload FROM statisticTable WHERE id_video=?", (item["item_id"],)).fetchone()
    con.close()
    assert date_upload == datetime.fromtimestamp(posted).strftime("%Y-%m-%d %H:%M:%S")


def test_radar_uses_real_posting_hours() -> None:
    from src.domain.analytics.channel_quality_radar import ChannelQualityRadar, VideoDataPoint

    videos = [
        VideoDataPoint(video_id="a", views=9000, likes=500, posted_hour=22),
        VideoDataPoint(video_id="b", views=8000, likes=400, posted_hour=22),
        VideoDataPoint(video_id="c", views=1000, likes=50, posted_hour=9),
    ]
    report = ChannelQualityRadar().analyze("x", videos)
    assert report.best_posting_hour == 22
    assert report.signals.hours_cv > 0


def test_radar_without_posting_hours_falls_back_to_profile_optimal_hour() -> None:
    from src.domain.analytics.channel_quality_radar import ChannelQualityRadar, VideoDataPoint

    videos = [VideoDataPoint(video_id=str(i), views=1000 + i, likes=50) for i in range(5)]  # hour unknown
    report = ChannelQualityRadar().analyze("x", videos, fallback_best_hour=22)
    assert report.best_posting_hour == 22
    assert report.signals.hours_cv == 0.0


def test_load_radar_inputs_carries_posting_hour(env) -> None:
    from src.infrastructure.tiktok.network_sniffer import TikTokNetworkSniffer
    from src.presentation.dialogs.channel_radar_dialog import load_radar_inputs, video_posted_hour

    posted = 1788223580
    TikTokNetworkSniffer(db_path=env["db"])._upsert_video_items(
        env["pid"], [{"item_id": "7600000000000000077", "create_time": str(posted), "play_count": "10"}]
    )
    _, videos = load_radar_inputs(env["profiles"], env["db"], env["pid"])
    assert video_posted_hour(videos[0]) == datetime.fromtimestamp(posted).hour
    assert video_posted_hour({"views": 1}) is None


# ---------------------------------------------------------------- 4. avatar egress


def test_avatar_downloads_directly_when_profile_opted_into_machine_ip(env) -> None:
    from src.infrastructure.tiktok import avatar_cache_service as mod

    env["profiles"].update(env["pid"], direct_connection=1)
    with patch.object(mod, "_http_get", return_value=b"PNG" + b"0" * 100) as get:
        path = mod.download_and_cache_avatar(env["pid"], "https://p16.tiktokcdn.com/a.jpg", db_path=env["db"])
    assert path
    assert get.call_args.args[1] is None  # direct: no proxy


def test_avatar_still_blocked_without_proxy_or_opt_in(env) -> None:
    from src.infrastructure.tiktok import avatar_cache_service as mod

    with patch.object(mod, "_http_get", side_effect=AssertionError("direct download from host IP")):
        assert mod.download_and_cache_avatar(env["pid"], "https://p16.tiktokcdn.com/a.jpg", db_path=env["db"]) is None
