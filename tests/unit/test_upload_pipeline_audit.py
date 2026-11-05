"""Upload pipeline audit: reservation lifecycle, scheduling, caption and isolation correctness.

Bugs covered (all found by reading the pipeline; offline, no real upload):
1. Auto-dispatch reserved a due video, then execute_upload() tried to reserve it again (requires
   'available') -> every scheduled upload failed and the video stayed 'reserved' forever.
2. Failures after the reservation (profile missing / DIE / CHECKPOINT, video row missing) raised
   before the error handler -> video stuck in 'reserved'.
3. A successful upload without publish_id was recorded as 'failed' (UI said success) -> retry
   would post a duplicate.
4. A past schedule_time (auto-dispatched at due time) was still sent to TikTok as a scheduled post.
5. Without a caption template the caption was the raw file name, e.g. "clip.mp4".
6. Post-upload isolation overwrote file_name (the caption) with the file name.
7. Ambiguous results (sent but unconfirmed) were marked 'failed' -> retry risks a duplicate post.
8. 'failed' videos disappeared from the queue table and could not be retried manually.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sammonny import UploadResult
from src.application.services.upload_service import UploadService
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.video_repository import VideoRepository


@pytest.fixture
def env(tmp_path: Path):
    db = tmp_path / "upload.db"
    run_all_migrations(db)
    profiles = ProfileRepository(db)
    videos = VideoRepository(db)
    adapter = MagicMock()
    adapter.upload_video.return_value = UploadResult(success=True, draft_id="d1", publish_id="7400000000000000001")
    service = UploadService(profile_repo=profiles, video_repo=videos, tiktok_adapter=adapter)
    pid = profiles.create({"name": "Uploader", "uuid": "uuid-up-0001", "status": "LIVE"})

    folder = tmp_path / "raw"
    folder.mkdir()

    def add_video(name: str = "my_clip.mp4", caption: str | None = None, schedule: str | None = None) -> int:
        f = folder / name
        f.write_bytes(name.encode() * 50)
        return videos.register_or_update(
            video_hash=f"h-{name}",
            file_path=str(f),
            file_name=caption or name,
            file_size=f.stat().st_size,
            mtime=f.stat().st_mtime,
            schedule_time=schedule,
            assigned_profile_id=pid,
        )

    return {
        "profiles": profiles,
        "videos": videos,
        "adapter": adapter,
        "service": service,
        "pid": pid,
        "add": add_video,
    }


def _status(env, vid: int) -> str:
    return env["videos"].get_by_id(vid)["status"]


def test_auto_dispatched_reservation_is_honoured(env):
    vid = env["add"]()
    assert env["videos"].try_reserve(video_id=vid, assigned_profile_id=env["pid"])  # what the scheduler does
    result = env["service"].execute_upload(video_id=vid, profile_id=env["pid"])
    assert result.success
    assert _status(env, vid) == "published"


def test_video_is_marked_uploading_while_publishing(env):
    vid = env["add"]()
    seen = []
    env["adapter"].upload_video.side_effect = lambda **kw: (
        seen.append(_status(env, vid)) or UploadResult(success=True, draft_id="d", publish_id="1")
    )
    env["service"].execute_upload(video_id=vid, profile_id=env["pid"])
    assert seen == ["uploading"]


@pytest.mark.parametrize("profile_status", ["DIE", "CHECKPOINT"])
def test_unusable_profile_does_not_leave_video_reserved(env, profile_status):
    vid = env["add"]()
    env["profiles"].update(env["pid"], status=profile_status)
    with pytest.raises(RuntimeError):
        env["service"].execute_upload(video_id=vid, profile_id=env["pid"])
    assert _status(env, vid) == "failed"
    env["adapter"].upload_video.assert_not_called()


def test_missing_profile_does_not_leave_video_reserved(env):
    vid = env["add"]()
    with pytest.raises(ValueError):
        env["service"].execute_upload(video_id=vid, profile_id=99999)
    assert _status(env, vid) != "reserved"


def test_success_without_publish_id_is_recorded_as_published(env):
    vid = env["add"]()
    env["adapter"].upload_video.return_value = UploadResult(success=True, draft_id="d", publish_id=None)
    result = env["service"].execute_upload(video_id=vid, profile_id=env["pid"])
    assert result.success
    assert _status(env, vid) == "published"


def test_ambiguous_result_is_not_marked_failed(env):
    vid = env["add"]()
    env["adapter"].upload_video.return_value = UploadResult(
        success=False, draft_id="d", error="timeout after send", is_ambiguous=True
    )
    env["service"].execute_upload(video_id=vid, profile_id=env["pid"])
    assert _status(env, vid) == "uploading", "unconfirmed upload must not be offered for retry (duplicate risk)"


def _sent_schedule(env) -> str | None:
    return env["adapter"].upload_video.call_args.kwargs["schedule_time"]


def test_past_schedule_time_is_published_immediately(env):
    past = (datetime.now() - timedelta(minutes=3)).strftime("%Y-%m-%d %H:%M:%S")
    vid = env["add"](schedule=past)
    env["service"].execute_upload(video_id=vid, profile_id=env["pid"])
    assert _sent_schedule(env) is None


def test_future_schedule_time_is_sent_to_tiktok(env):
    future = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    vid = env["add"](schedule=future)
    env["service"].execute_upload(video_id=vid, profile_id=env["pid"])
    assert _sent_schedule(env) == future


def test_schedule_beyond_tiktok_window_is_not_sent(env):
    far = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    vid = env["add"](schedule=far)
    env["service"].execute_upload(video_id=vid, profile_id=env["pid"])
    assert _sent_schedule(env) is None


def test_file_name_caption_has_no_extension(env):
    vid = env["add"]("my_clip.mp4")
    env["service"].execute_upload(video_id=vid, profile_id=env["pid"])
    assert env["adapter"].upload_video.call_args.kwargs["title"] == "my_clip"


def test_real_caption_is_kept_verbatim(env):
    vid = env["add"]("a.mp4", caption="Hello world #fyp #viral")
    env["service"].execute_upload(video_id=vid, profile_id=env["pid"])
    kwargs = env["adapter"].upload_video.call_args.kwargs
    assert kwargs["title"] == "Hello world #fyp #viral"
    assert kwargs["tags"] == ["#fyp", "#viral"]


def test_isolation_keeps_caption(env):
    vid = env["add"]("b.mp4", caption="Caption giữ nguyên #fyp")
    env["service"].execute_upload(video_id=vid, profile_id=env["pid"])
    row = env["videos"].get_by_id(vid)
    assert row["file_name"] == "Caption giữ nguyên #fyp"
    assert "_posted" in Path(row["file_path"]).parts


def test_failed_video_stays_visible_and_can_be_retried(env):
    vid = env["add"]()
    env["adapter"].upload_video.return_value = UploadResult(success=False, draft_id="d", error="boom")
    env["service"].execute_upload(video_id=vid, profile_id=env["pid"])
    assert _status(env, vid) == "failed"
    assert vid in [v["id"] for v in env["videos"].list_available(only_available=False)]

    env["adapter"].upload_video.return_value = UploadResult(success=True, draft_id="d", publish_id="2")
    assert env["service"].execute_upload(video_id=vid, profile_id=env["pid"]).success
    assert _status(env, vid) == "published"


def test_video_already_uploading_is_not_touched_by_a_second_attempt(env):
    vid = env["add"]()
    env["videos"].try_reserve(video_id=vid, assigned_profile_id=env["pid"])
    env["service"].video_repo.claim_for_upload(video_id=vid, profile_id=env["pid"])  # first worker
    with pytest.raises(RuntimeError):
        env["service"].execute_upload(video_id=vid, profile_id=env["pid"])
    assert _status(env, vid) == "uploading"


def test_main_window_does_not_isolate_again_after_upload(qtbot, tmp_path: Path):
    """UploadService already isolates under the profile lock; a second move from the GUI side raced it."""
    src = Path("src/presentation/views/main_window.py").read_text(encoding="utf-8")
    start = src.index("    def _on_upload_completed(")
    body = src[start : src.index("\n    def ", start + 10)]
    assert "isolate_video_file" not in body
