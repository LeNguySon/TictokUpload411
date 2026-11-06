"""
TDD Test Suite for Unified TikTok Video Auto-Upload Pipeline, SDK Inheritance,
Folder Distribution Algorithm, and Safety Policies.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sammonny import RemoteStatus, UploadMode, UploadResult
from src.application.services.upload_service import UploadService
from src.domain.policies.upload_policy import (
    calculate_stall_timeout,
    clamp_caption,
    get_profile_upload_lock,
    spin_caption,
)
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.video_repository import VideoRepository
from src.infrastructure.tiktok.sammonny_adapter import SamMonnyTikTokAdapter
from src.presentation.dialogs.batch_folder_upload_dialog import BatchFolderUploadDialog


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    db_file = tmp_path / "test_auto_upload.db"
    run_all_migrations(db_file)
    return db_file


def test_clamp_caption_preserves_hashtags_and_limits_length() -> None:
    # Short caption stays intact
    short_cap = "Cute dancing cat! #cat #cute #trend"
    assert clamp_caption(short_cap, max_chars=100) == short_cap

    # Very long caption exceeding 2200 characters
    long_body = "This is a great video " * 120  # ~2640 chars
    hashtags = "#fyp #viral #tiktok2026 #explore"
    full_cap = f"{long_body} {hashtags}"

    clamped = clamp_caption(full_cap, max_chars=2200)
    assert len(clamped) <= 2200
    assert "#fyp" in clamped
    assert "#viral" in clamped
    assert "#tiktok2026" in clamped
    assert "#explore" in clamped
    assert clamped.endswith(hashtags)


def test_spin_caption_resolves_spintax_and_placeholders() -> None:
    template = "{Tuyệt phẩm|Đỉnh cao} của {title} quay từ {filename} #mmo"
    resolved = spin_caption(template, title="Khám Phá Vũ Trụ", filename="galaxy.mp4")

    assert ("Tuyệt phẩm" in resolved) or ("Đỉnh cao" in resolved)
    assert "Khám Phá Vũ Trụ" in resolved
    assert "galaxy.mp4" in resolved
    assert "#mmo" in resolved
    assert "{" not in resolved
    assert "}" not in resolved


def test_calculate_stall_timeout() -> None:
    # Small file (10MB) -> clamp at min 60.0s
    assert calculate_stall_timeout(10.0) == 64.0
    # Zero MB -> min 60.0s
    assert calculate_stall_timeout(0.0) == 60.0
    # Large file (500MB) -> clamp at max 180.0s
    assert calculate_stall_timeout(500.0) == 180.0
    # Normal 100MB file -> 60 + 100*0.4 = 100.0s
    assert calculate_stall_timeout(100.0) == 100.0


def test_get_profile_upload_lock_is_thread_safe_singleton() -> None:
    lock1 = get_profile_upload_lock(42)
    lock2 = get_profile_upload_lock(42)
    lock_other = get_profile_upload_lock(99)

    assert lock1 is lock2
    assert lock1 is not lock_other


def test_sammonny_adapter_tri_modal_mode_selection(tmp_path: Path) -> None:
    mock_vault = MagicMock()
    mock_vault.get_oauth_tokens.return_value = {"access_token": "valid_oauth_token_123"}

    mock_direct_client = MagicMock()
    mock_direct_client.query_creator_info.return_value = {
        "privacy_level_options": ["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY"],
        "max_video_post_duration_sec": 600,
    }
    mock_direct_client.init_direct_post.return_value = {
        "publish_id": "pub_mock_111",
        "upload_url": "https://upload.tiktok.com/v2/mock",
        "chunk_size": 10485760,
    }
    mock_direct_client.upload_video_chunks.return_value = 1024

    adapter = SamMonnyTikTokAdapter(
        vault=mock_vault,
        direct_client=mock_direct_client,
        preferred_mode=UploadMode.OFFICIAL_DIRECT_POST,
    )
    adapter._profile_egress = lambda _pid: "http://proxy.test:8080"  # test profiles have a proxy

    dummy_video = tmp_path / "sample.mp4"
    dummy_video.write_bytes(b"dummy video data for upload")

    # Execute upload
    result: UploadResult = adapter.upload_video(
        profile_id=1,
        video_path=dummy_video,
        title="Sample Video",
        privacy="PUBLIC_TO_EVERYONE",
        tags=["#test", "#trend"],
    )

    assert result.success is True
    assert result.publish_id == "pub_mock_111"
    assert result.status == RemoteStatus.PROCESSING_UPLOAD


def test_upload_service_distribute_folder_videos_to_queue(temp_db: Path, tmp_path: Path) -> None:
    profile_repo = ProfileRepository(temp_db)
    video_repo = VideoRepository(temp_db)
    mock_adapter = MagicMock()

    # Create 2 test profiles
    p1 = profile_repo.create({"name": "Chan1", "username_on_tiktok": "acc1", "country": "US"})
    p2 = profile_repo.create({"name": "Chan2", "username_on_tiktok": "acc2", "country": "VN"})

    # Create a test folder with 4 videos
    folder = tmp_path / "videos_batch"
    folder.mkdir()
    v1 = folder / "clip1.mp4"
    v2 = folder / "clip2.mov"
    v3 = folder / "clip3.mp4"
    v4 = folder / "clip4.mkv"
    v1.write_bytes(b"video 1 content")
    v2.write_bytes(b"video 2 content")
    v3.write_bytes(b"video 3 content")
    v4.write_bytes(b"video 4 content")

    upload_service = UploadService(
        profile_repo=profile_repo,
        video_repo=video_repo,
        tiktok_adapter=mock_adapter,
    )

    # Distribute videos
    distributed = upload_service.distribute_folder_videos_to_queue(
        folder_path=folder,
        profile_ids=[p1, p2],
        min_interval_hours=2.0,
        random_order=False,
        caption_template="{title} #trending",
    )

    assert len(distributed) == 4
    # Fair-share Round Robin: 2 videos each
    p1_items = [d for d in distributed if d["assigned_profile_id"] == p1]
    p2_items = [d for d in distributed if d["assigned_profile_id"] == p2]
    assert len(p1_items) == 2
    assert len(p2_items) == 2

    # Check database records
    available = video_repo.list_available()
    assert len(available) == 4

    # Deduplication test: re-running distribution on same folder skips claimed videos
    redistributed = upload_service.distribute_folder_videos_to_queue(
        folder_path=folder,
        profile_ids=[p1, p2],
        deduplicate=True,
    )
    assert len(redistributed) == 0, "All videos were already indexed; deduplication must return 0"


def test_batch_folder_upload_dialog_instantiation(qapp, temp_db: Path) -> None:
    profile_repo = ProfileRepository(temp_db)
    video_repo = VideoRepository(temp_db)
    mock_adapter = MagicMock()

    # Pre-populate profiles
    profile_repo.create({"name": "Profile_Alpha", "username_on_tiktok": "alpha_user", "country": "US"})
    profile_repo.create({"name": "Profile_Beta", "username_on_tiktok": "beta_user", "country": "VN"})

    upload_service = UploadService(
        profile_repo=profile_repo,
        video_repo=video_repo,
        tiktok_adapter=mock_adapter,
    )

    dialog = BatchFolderUploadDialog(
        profile_repo=profile_repo,
        upload_service=upload_service,
    )

    assert "Nạp Thư Mục" in dialog.windowTitle() and "Batch Upload" in dialog.windowTitle()
    assert dialog.profile_table.rowCount() == 2
    assert dialog.chk_shuffle.isChecked() is True
    assert dialog.chk_deduplicate.isChecked() is True
    assert dialog.chk_allow_hd.isChecked() is True
