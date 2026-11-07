"""
TikTok Studio 2026 `/tiktok/creator/manage/item_list/v1/` puts each video's counters at the item's TOP level,
as strings (`play_count`, `like_count`, `comment_count`, `share_count`) and the duration in milliseconds.
The sniffer only read nested `stats{}` / `views` keys, so every video was stored with 0 views (seen live on
@swall.pain: 50/50 videos at 0), which turned the radar's low-view alert into a false "flop" alarm.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.tiktok.network_sniffer import TikTokNetworkSniffer

URL = "https://www.tiktok.com/tiktok/creator/manage/item_list/v1/"


def _studio_item(item_id: str, plays: str, likes: str, comments: str, shares: str, age_days: int) -> dict:
    return {
        "item_id": item_id,
        "desc": "",
        "create_time": str(int(time.time()) - age_days * 86400),
        "post_time": str(int(time.time()) - age_days * 86400),
        "play_count": plays,
        "like_count": likes,
        "comment_count": comments,
        "share_count": shares,
        "favorite_count": "1",
        "duration": 33112,  # milliseconds in this API
        "status": 102,
        "visibility": 1,
    }


@pytest.fixture
def env(tmp_path: Path) -> dict:
    db = tmp_path / "studio.db"
    run_all_migrations(db)
    pid = ProfileRepository(db).create({"name": "studio", "status": "LIVE"})
    return {"db": db, "pid": pid}


def test_studio_item_list_top_level_string_counters_are_stored(env) -> None:
    body = {
        "status_code": 0,
        "item_list": [
            _studio_item("7600000000000000001", "843", "57", "4", "2", age_days=3),
            _studio_item("7600000000000000002", "120", "9", "0", "1", age_days=45),
        ],
    }
    sniffer = TikTokNetworkSniffer(db_path=env["db"])
    assert sniffer.process_api_response(env["pid"], URL, body)

    con = sqlite3.connect(env["db"])
    rows = {
        r[0]: r[1:]
        for r in con.execute(
            "SELECT id_video, views, likes, comments, shares FROM statisticTable WHERE profile_id=?", (env["pid"],)
        )
    }
    vt = dict(con.execute("SELECT video_id, duration FROM videoTables WHERE profile_id=?", (env["pid"],)).fetchall())
    con.close()

    assert rows["7600000000000000001"] == (843, 57, 4, 2)
    assert rows["7600000000000000002"] == (120, 9, 0, 1)
    assert vt["7600000000000000001"] == 33  # seconds, not 33112


def test_studio_item_list_month_views_counts_only_last_30_days(env) -> None:
    sniffer = TikTokNetworkSniffer(db_path=env["db"])
    items = [
        _studio_item("7600000000000000011", "1000", "1", "0", "0", age_days=2),
        _studio_item("7600000000000000012", "500", "1", "0", "0", age_days=40),
    ]
    result = sniffer._upsert_video_items(env["pid"], items)
    assert result["views_month"] == 1000
