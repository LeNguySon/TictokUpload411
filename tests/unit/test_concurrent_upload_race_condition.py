"""Concurrency unit tests verifying thread safety and absence of race conditions
during concurrent multi-profile video uploads.
Following ECC TDD (Test-Driven Development) methodology.
"""

from __future__ import annotations

import concurrent.futures
import time
from unittest.mock import MagicMock, patch

from sammonny.platforms.tiktok import RemoteStatus, TikTokPublisherAdapter, UploadMode, UploadResult


def test_publisher_adapter_accepts_stateless_preferred_mode_parameter() -> None:
    """Tests that TikTokPublisherAdapter.upload accepts preferred_mode as a parameter
    without mutating self.preferred_mode.
    """
    mock_session = MagicMock()
    mock_sf = MagicMock(return_value=mock_session)

    adapter = TikTokPublisherAdapter(session_factory=mock_sf, preferred_mode=None)

    fake_draft = MagicMock()
    fake_draft.draft_id = "draft_test"
    fake_draft.file_path = "video.mp4"
    fake_draft.title = "Test Video"
    fake_draft.tags = []
    fake_draft.privacy = "Public"
    fake_draft.allow_comment = True
    fake_draft.allow_duet = True
    fake_draft.allow_stitch = True
    fake_draft.schedule_time = None

    with patch("sammonny.platforms.tiktok.TikTokHybridApiUploader") as mock_hybrid_cls:
        mock_hybrid_instance = MagicMock()
        mock_hybrid_instance.upload_via_hybrid.return_value = UploadResult(
            success=True,
            draft_id="draft_test",
            publish_id="pub_123",
            status=RemoteStatus.PUBLISH_COMPLETE,
        )
        mock_hybrid_cls.return_value = mock_hybrid_instance

        # Call upload with explicit preferred_mode=COOKIE_API_HYBRID
        res = adapter.upload(
            draft=fake_draft,
            account_id="acc_hybrid",
            preferred_mode=UploadMode.COOKIE_API_HYBRID,
        )

        assert res.success is True
        # Verify instance attribute preferred_mode was NOT mutated!
        assert adapter.preferred_mode is None
        # Verify local session was closed in finally
        mock_session.close.assert_called_once()


def test_concurrent_upload_preserves_per_profile_mode() -> None:
    """Simulates 2 concurrent threads uploading videos simultaneously:
    - Thread A: Profile 101 with OAuth token -> OFFICIAL_DIRECT_POST
    - Thread B: Profile 102 with Cookie only -> COOKIE_API_HYBRID
    Verifies that neither thread clobbers the other's upload mode or session factory.
    """
    from src.infrastructure.tiktok.sammonny_adapter import SamMonnyTikTokAdapter

    mock_vault = MagicMock()
    # Profile 101 has OAuth access token, Profile 102 does NOT
    mock_vault.get_oauth_tokens.side_effect = lambda pid: (
        {"access_token": "valid_token_101"} if str(pid) == "101" else {}
    )

    mock_direct_client = MagicMock()
    mock_direct_client.query_creator_info.return_value = {
        "privacy_level_options": ["PUBLIC_TO_EVERYONE", "SELF_ONLY"],
        "max_video_post_duration_sec": 600,
    }
    mock_direct_client.init_direct_post.return_value = {
        "publish_id": "oauth_pub_101",
        "upload_url": "https://direct.tiktok.com/upload",
        "chunk_size": 10 * 1024 * 1024,
    }
    mock_direct_client.upload_video_chunks.return_value = 1024

    mock_session_102 = MagicMock()
    mock_sf = MagicMock(return_value=mock_session_102)

    adapter = SamMonnyTikTokAdapter(
        vault=mock_vault,
        direct_client=mock_direct_client,
        session_factory=mock_sf,
        preferred_mode=None,
    )

    executed_modes: list[str] = []

    def run_upload_profile_101() -> UploadResult:
        # Give small sleep to simulate concurrency overlap
        time.sleep(0.05)
        with patch("builtins.open", MagicMock()):
            res = adapter.upload_video(
                profile_id=101,
                video_path="scratch/video1.mp4",
                title="Video OAuth 101",
            )
            executed_modes.append(f"101:{res.publish_id}")
            return res

    def run_upload_profile_102() -> UploadResult:
        with patch("sammonny.platforms.tiktok.TikTokHybridApiUploader") as mock_hybrid_cls:
            mock_hybrid_instance = MagicMock()
            mock_hybrid_instance.upload_via_hybrid.return_value = UploadResult(
                success=True,
                draft_id="draft_102",
                publish_id="hybrid_pub_102",
                status=RemoteStatus.PUBLISH_COMPLETE,
            )
            mock_hybrid_cls.return_value = mock_hybrid_instance

            res = adapter.upload_video(
                profile_id=102,
                video_path="scratch/video2.mp4",
                title="Video Cookie 102",
            )
            executed_modes.append(f"102:{res.publish_id}")
            return res

    with patch.object(adapter.publisher, "create_draft") as mock_create_draft:
        draft_mock = MagicMock()
        draft_mock.draft_id = "test_draft"
        draft_mock.file_path = "video.mp4"
        draft_mock.title = "Title"
        draft_mock.tags = []
        draft_mock.privacy = "SELF_ONLY"
        draft_mock.allow_comment = True
        draft_mock.allow_duet = True
        draft_mock.allow_stitch = True
        draft_mock.schedule_time = None
        draft_mock.file_size_bytes = 1024
        draft_mock.cover_timestamp_ms = 1000
        mock_create_draft.return_value = draft_mock

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            fut_a = executor.submit(run_upload_profile_101)
            fut_b = executor.submit(run_upload_profile_102)

            res_a = fut_a.result(timeout=5.0)
            res_b = fut_b.result(timeout=5.0)

    # Assert Thread A (Profile 101) succeeded with OAuth Direct Post
    assert res_a.success is True
    assert res_a.publish_id == "oauth_pub_101"

    # Assert Thread B (Profile 102) succeeded with Hybrid
    assert res_b.success is True
    assert res_b.publish_id == "hybrid_pub_102"

    # Verify adapter.preferred_mode was NOT permanently overwritten
    assert adapter.preferred_mode is None
    assert adapter.publisher.preferred_mode is None
