"""Folder distribution ("Nạp thư mục phân bổ video"), checked on a copy of the real DB on 2026-11-07:

1. invalid files (0-byte .mp4, .avi that the validation policy rejects) were queued and only failed at upload time;
2. the interval was applied to the whole batch: 3 channels x 12 h meant one video per channel every 36 h;
3. new slots started at now + 5 min whatever the channel already had queued (2 h after an existing video);
4. the dialog options (comment / duet / stitch / HD / AI label / privacy) were never stored, so uploads always
   used the defaults: an "AI-generated" video was published WITHOUT TikTok's AI label.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sammonny import RemoteStatus, UploadResult
from src.application.services.upload_service import UploadService
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
from src.infrastructure.database.repositories.video_repository import VideoRepository

FMT = "%Y-%m-%d %H:%M:%S"


@pytest.fixture
def env(tmp_path: Path):
    db = tmp_path / "app.db"
    run_all_migrations(db)
    profiles = ProfileRepository(db)
    videos = VideoRepository(db)
    pids = [profiles.create({"name": f"ch{i}", "uuid": f"u-{i}", "status": "LIVE"}) for i in range(3)]
    proxy_id = ProxyRepository(db).create(host="10.0.0.1", port=8080)
    for pid in pids:
        profiles.update(pid, proxy_id=proxy_id)
    adapter = MagicMock()
    adapter.upload_video.return_value = UploadResult(success=True, draft_id="d", publish_id="p",
                                                     status=RemoteStatus.PROCESSING_UPLOAD)
    adapter.supports_native_schedule.return_value = True
    svc = UploadService(profile_repo=profiles, video_repo=videos, tiktok_adapter=adapter)
    folder = tmp_path / "videos"
    folder.mkdir()
    return {"svc": svc, "videos": videos, "pids": pids, "folder": folder, "adapter": adapter, "tmp": tmp_path}


def _clips(folder: Path, n: int) -> None:
    for i in range(n):
        (folder / f"clip_{i}.mp4").write_bytes(os.urandom(4096))


def _batch(env, **kw):
    return env["svc"].distribute_multi_project_batches(
        [{"project_id": 1, "project_name": "P", "folder_path": str(env["folder"]), "profile_ids": env["pids"]}],
        prioritize_newest=False, **kw
    )


def _times(items, pid):
    return sorted(datetime.strptime(i["schedule_time"], FMT) for i in items if i["assigned_profile_id"] == pid)


def test_invalid_files_are_not_queued(env):
    _clips(env["folder"], 2)
    (env["folder"] / "empty.mp4").write_bytes(b"")
    (env["folder"] / "old.avi").write_bytes(os.urandom(4096))  # the upload validation rejects .avi
    items = _batch(env)
    assert sorted(Path(i["file_path"]).name for i in items) == ["clip_0.mp4", "clip_1.mp4"]


def test_interval_applies_per_channel(env):
    _clips(env["folder"], 9)
    start = datetime.now()
    items = _batch(env, min_interval_hours=12)
    for pid in env["pids"]:
        times = _times(items, pid)
        assert len(times) == 3
        assert times[0] - start < timedelta(minutes=10)  # every channel starts right away, in parallel
        assert [round((b - a).total_seconds() / 3600, 2) for a, b in zip(times, times[1:], strict=False)] == [12, 12]
    assert max(max(_times(items, p)) for p in env["pids"]) - start < timedelta(hours=24, minutes=10)


def test_single_folder_entry_point_uses_the_same_rules(env):
    _clips(env["folder"], 6)
    (env["folder"] / "empty.mp4").write_bytes(b"")
    items = env["svc"].distribute_folder_videos_to_queue(
        folder_path=env["folder"], profile_ids=env["pids"], min_interval_hours=6, random_order=False
    )
    assert len(items) == 6
    for pid in env["pids"]:
        a, b = _times(items, pid)
        assert round((b - a).total_seconds() / 3600, 2) == 6


def test_new_slots_keep_the_interval_after_videos_already_queued(env):
    pid = env["pids"][0]
    existing = env["tmp"] / "pre.mp4"
    existing.write_bytes(os.urandom(4096))
    slot = (datetime.now() + timedelta(hours=2)).replace(microsecond=0)
    env["videos"].register_or_update("prehash", str(existing), "pre.mp4", 4096, 0.0, assigned_profile_id=pid,
                                     schedule_time=slot.strftime(FMT))
    _clips(env["folder"], 3)
    items = _batch(env, min_interval_hours=12)
    first_new = _times(items, pid)[0]
    assert first_new - slot >= timedelta(hours=12)


def test_dialog_options_are_stored_and_used_by_the_upload(env):
    _clips(env["folder"], 1)
    items = _batch(env, privacy="SELF_ONLY", allow_comment=False, allow_duet=False, allow_stitch=False,
                   allow_hd=False, is_ai_generated=True)
    row = env["videos"].get_by_id(items[0]["id"])
    assert row is not None
    assert (row["privacy"], row["allow_comment"], row["allow_duet"], row["allow_stitch"], row["allow_hd"],
            row["is_ai_generated"]) == ("SELF_ONLY", 0, 0, 0, 0, 1)

    env["svc"].execute_upload(video_id=items[0]["id"], profile_id=items[0]["assigned_profile_id"])
    kw = env["adapter"].upload_video.call_args.kwargs
    assert kw["privacy"] == "SELF_ONLY"
    assert (kw["allow_comment"], kw["allow_duet"], kw["allow_stitch"], kw["allow_hd"], kw["is_ai_generated"]) == (
        False, False, False, False, True)


def test_videos_queued_elsewhere_keep_the_default_options(env):
    """Rows created by other paths (single import, older databases) still upload with the usual defaults."""
    clip = env["tmp"] / "single.mp4"
    clip.write_bytes(os.urandom(4096))
    vid = env["videos"].register_or_update("h1", str(clip), "single.mp4", 4096, 0.0,
                                           assigned_profile_id=env["pids"][0])
    env["svc"].execute_upload(video_id=vid, profile_id=env["pids"][0])
    kw = env["adapter"].upload_video.call_args.kwargs
    assert kw["privacy"] == "PUBLIC_TO_EVERYONE"
    assert (kw["allow_comment"], kw["allow_duet"], kw["allow_stitch"], kw["allow_hd"], kw["is_ai_generated"]) == (
        True, True, True, True, False)


def test_dialog_interval_label_says_per_channel(qtbot):
    from src.presentation.dialogs import batch_folder_upload_dialog as m

    assert "cùng 1 kênh" in m.INTERVAL_LABEL


def test_dialog_folder_count_matches_what_will_be_queued(tmp_path):
    from src.presentation.dialogs.batch_folder_upload_dialog import count_valid_videos_in_folder

    _clips(tmp_path, 2)
    (tmp_path / "empty.mp4").write_bytes(b"")
    (tmp_path / "old.avi").write_bytes(os.urandom(4096))
    (tmp_path / "_posted").mkdir()
    (tmp_path / "_posted" / "done.mp4").write_bytes(os.urandom(4096))
    assert count_valid_videos_in_folder(str(tmp_path)) == 2
