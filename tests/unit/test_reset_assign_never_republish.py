"""a1905db shows published videos in the queue and adds "Đặt lại Sẵn sàng / Thử lại" + "Gán Tài Khoản" actions.
Resetting turned ANY status back to 'available': a published video (or one being uploaded) picked by mistake was
queued again and the scheduler would post it a second time."""

from __future__ import annotations

from pathlib import Path

import pytest
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.video_repository import VideoRepository


@pytest.fixture
def repo(tmp_path: Path):
    db = tmp_path / "app.db"
    run_all_migrations(db)
    pid = ProfileRepository(db).create({"name": "p"})
    videos = VideoRepository(db)
    ids = {}
    for status in ("available", "reserved", "uploading", "published", "failed"):
        vid = videos.register_or_update(f"h-{status}", f"{status}.mp4", f"{status}.mp4", 4096, 0.0,
                                        assigned_profile_id=pid)
        from src.infrastructure.database.connection import db_session

        with db_session(db) as conn:
            conn.execute("UPDATE video_registry SET status=?, error_message='x' WHERE id=?", (status, vid))
        ids[status] = vid
    return videos, ids, ProfileRepository(db).create({"name": "q"})


def _status(videos, vid):
    return videos.get_by_id(vid)["status"]


def test_reset_never_requeues_published_or_uploading_videos(repo):
    videos, ids, _ = repo
    count = videos.reset_status_to_available(list(ids.values()))
    assert _status(videos, ids["published"]) == "published"
    assert _status(videos, ids["uploading"]) == "uploading"
    assert _status(videos, ids["failed"]) == "available"
    assert _status(videos, ids["reserved"]) == "available"
    assert count == 3  # available (error cleared), reserved, failed


def test_assign_never_moves_published_or_uploading_videos(repo):
    videos, ids, other = repo
    count = videos.assign_profile_to_videos(other, list(ids.values()))
    assert videos.get_by_id(ids["published"])["assigned_profile_id"] != other
    assert videos.get_by_id(ids["uploading"])["assigned_profile_id"] != other
    assert videos.get_by_id(ids["failed"])["assigned_profile_id"] == other
    assert count == 3


def test_reset_message_says_how_many_were_skipped(repo, qtbot):
    from types import SimpleNamespace
    from unittest.mock import patch

    from src.presentation.views.main_window import TikTokManagerMainWindow

    videos, ids, _ = repo
    fake = SimpleNamespace(video_repo=videos, refresh_videos=lambda: None)
    with patch("src.presentation.views.main_window.InfoBar") as info:
        TikTokManagerMainWindow._on_reset_videos_status(fake, list(ids.values()))
    content = info.success.call_args.kwargs["content"]
    assert "3 video" in content and "bỏ qua 2" in content
