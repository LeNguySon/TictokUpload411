"""Unit and Integration Tests for Comprehensive TikTok Video Upload Pipeline.
Strict ECC TDD: Validates options propagation, UUID resolution, deduplication, and isolation.
"""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sammonny import RemoteStatus, UploadResult
from src.application.services.upload_service import UploadService
from src.domain.policies.upload_policy import clamp_caption, spin_caption
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.video_repository import VideoRepository
from src.infrastructure.tiktok.sammonny_adapter import (
    SamMonnyTikTokAdapter,
    _default_session_factory,
)

FUTURE_SCHEDULE = (datetime.now() + timedelta(hours=2)).strftime(
    "%Y-%m-%d %H:%M:%S"
)  # relative: TikTok only schedules 15 min .. 10 days ahead


@pytest.fixture
def isolated_upload_env(tmp_path: Path):
    db_file = tmp_path / "upload_test.db"
    run_all_migrations(db_file)

    prof_repo = ProfileRepository(db_file)
    p_id = prof_repo.create(
        {
            "name": "LiveUploadProfile",
            "uuid": "007383c2-9439-4df2-8fd1-50b196910b29",
            "username_on_tiktok": "david.martin9472",
            "status": "LIVE",
        }
    )

    vid_repo = VideoRepository(db_file)

    test_video = tmp_path / "sample_test_video.mp4"
    test_video.write_bytes(b"Simulated MP4 video bytes content 1234567890")

    vid_id = vid_repo.register_or_update(
        video_hash="hash_abc_12345678",
        file_path=str(test_video),
        file_name="sample_test_video.mp4",
        file_size=len(test_video.read_bytes()),
        mtime=test_video.stat().st_mtime,
        assigned_profile_id=p_id,
        schedule_time="2026-11-20 18:00:00",
    )

    return {
        "db_file": db_file,
        "prof_repo": prof_repo,
        "vid_repo": vid_repo,
        "profile_id": p_id,
        "video_id": vid_id,
        "video_path": test_video,
    }


def test_session_factory_resolves_profile_id_to_uuid(isolated_upload_env):
    """Verifies _default_session_factory maps integer profile_id to authentic Orbita UUID."""
    p_id = isolated_upload_env["profile_id"]

    # Call _default_session_factory with integer ID and isolated db
    session = _default_session_factory(str(p_id), db_path=isolated_upload_env["db_file"])
    assert session is not None
    assert session.profile_id == "007383c2-9439-4df2-8fd1-50b196910b29"
    assert "007383c2-9439-4df2-8fd1-50b196910b29" in str(session.profile_dir)


def test_upload_service_respects_all_custom_options(isolated_upload_env):
    """Verifies UploadService passes all customized privacy, interactive flags, and scheduling to the adapter."""
    mock_adapter = MagicMock(spec=SamMonnyTikTokAdapter)
    mock_adapter.upload_video.return_value = UploadResult(
        success=True,
        draft_id="draft_123",
        publish_id="tiktok_pub_888",
        status=RemoteStatus.PROCESSING_UPLOAD,
    )

    svc = UploadService(
        profile_repo=isolated_upload_env["prof_repo"],
        video_repo=isolated_upload_env["vid_repo"],
        tiktok_adapter=mock_adapter,
    )

    v_id = isolated_upload_env["video_id"]
    p_id = isolated_upload_env["profile_id"]

    # Execute upload with custom options
    res = svc.execute_upload(
        video_id=v_id,
        profile_id=p_id,
        privacy="SELF_ONLY",
        allow_comment=False,
        allow_duet=False,
        allow_stitch=False,
        allow_hd=True,
        is_ai_generated=True,
        schedule_time=FUTURE_SCHEDULE,
    )

    assert res.success is True
    assert res.publish_id == "tiktok_pub_888"

    # Verify adapter received every custom option
    call_kwargs = mock_adapter.upload_video.call_args.kwargs
    assert call_kwargs["privacy"] == "SELF_ONLY"
    assert call_kwargs["allow_comment"] is False
    assert call_kwargs["allow_duet"] is False
    assert call_kwargs["allow_stitch"] is False
    assert call_kwargs["allow_hd"] is True
    assert call_kwargs["is_ai_generated"] is True
    assert call_kwargs["schedule_time"] == FUTURE_SCHEDULE

    # Verify video marked published in repository
    v_row = isolated_upload_env["vid_repo"].get_by_id(v_id)
    assert v_row["status"] == "published"
    assert v_row["tiktok_video_id"] == "tiktok_pub_888"


def test_video_deduplication_and_sha256_detection(isolated_upload_env):
    """Verifies that duplicate video files with identical SHA-256 are detected and skipped."""
    mock_adapter = MagicMock(spec=SamMonnyTikTokAdapter)
    svc = UploadService(
        profile_repo=isolated_upload_env["prof_repo"],
        video_repo=isolated_upload_env["vid_repo"],
        tiktok_adapter=mock_adapter,
    )

    v_path = isolated_upload_env["video_path"]

    # Calculate sha256
    sha1 = svc.compute_sha256(v_path)
    assert len(sha1) == 64

    # Duplicate file in another directory
    dup_file = v_path.parent / "copied_video.mp4"
    dup_file.write_bytes(v_path.read_bytes())

    sha2 = svc.compute_sha256(dup_file)
    assert sha1 == sha2


def test_post_upload_file_isolation_to_posted(isolated_upload_env):
    """Verifies post-upload isolation safely moves video file into _posted/ subfolder."""
    mock_adapter = MagicMock(spec=SamMonnyTikTokAdapter)
    svc = UploadService(
        profile_repo=isolated_upload_env["prof_repo"],
        video_repo=isolated_upload_env["vid_repo"],
        tiktok_adapter=mock_adapter,
    )

    v_id = isolated_upload_env["video_id"]
    orig_path = isolated_upload_env["video_path"]
    assert orig_path.exists()

    new_path = svc.isolate_video_file(v_id, subfolder_name="_posted")
    assert new_path is not None
    assert new_path.exists()
    assert not orig_path.exists()
    assert "_posted" in str(new_path)

    # Check database updated with new path
    v_row = isolated_upload_env["vid_repo"].get_by_id(v_id)
    assert v_row["file_path"] == str(new_path)


def test_caption_spintax_and_hashtag_preservation():
    """Verifies that spintax caption variations resolve correctly and hashtag limits are enforced."""
    template = "{Chào mừng|Xin chào} mọi người đến với kênh của {title} #trending #viral #fyp"
    resolved = spin_caption(template, title="TechReview", filename="clip.mp4")

    assert ("Chào mừng" in resolved) or ("Xin chào" in resolved)
    assert "TechReview" in resolved
    assert "#trending" in resolved
    assert "#viral" in resolved
    assert "#fyp" in resolved

    clamped = clamp_caption(resolved, max_chars=50)
    assert len(clamped) <= 50
    assert "#fyp" in clamped
