"""
Unit tests for SamMonnyTikTokAdapter.
Strict TDD - Phase 2 (RED)
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from sammonny import CapabilityResult, RemoteStatus, UploadMode, UploadResult
from src.infrastructure.tiktok.sammonny_adapter import SamMonnyTikTokAdapter


def test_sammonny_adapter_initialization():
    adapter = SamMonnyTikTokAdapter()
    assert adapter is not None
    assert adapter.direct_client is not None
    assert adapter.publisher is not None


def test_sammonny_adapter_upload_direct_post():
    mock_vault = MagicMock()
    mock_vault.get_oauth_tokens.return_value = {
        "access_token": "act_valid_token_12345",
        "refresh_token": "rft_refresh_67890",
    }

    adapter = SamMonnyTikTokAdapter(vault=mock_vault)

    # Create dummy video file
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(b"\x00" * 2048)
        video_path = f.name

    try:
        # Mock publisher validate_capability & upload
        mock_cap = CapabilityResult(
            authorized=True,
            mode=UploadMode.OFFICIAL_DIRECT_POST,
            account_id="101",
            creator_info={"creator_nickname": "TestCreator"},
        )
        mock_result = UploadResult(
            success=True,
            draft_id="draft_123",
            publish_id="v_pub_tiktok_999",
            status=RemoteStatus.PROCESSING_UPLOAD,
            bytes_uploaded=2048,
            total_bytes=2048,
            elapsed_sec=1.2,
        )

        with (
            patch.object(adapter.publisher, "validate_capability", return_value=mock_cap),
            patch.object(adapter.publisher, "upload", return_value=mock_result),
        ):
            result = adapter.upload_video(
                profile_id=101,
                video_path=video_path,
                title="Amazing Dance Video #trend",
                privacy="PUBLIC_TO_EVERYONE",
            )

            assert result.success is True
            assert result.publish_id == "v_pub_tiktok_999"
            mock_vault.get_oauth_tokens.assert_called_once_with(101)
    finally:
        Path(video_path).unlink(missing_ok=True)


def test_sammonny_adapter_creator_metrics_fetch():
    mock_vault = MagicMock()
    mock_vault.get_oauth_tokens.return_value = {"access_token": "valid_token"}

    adapter = SamMonnyTikTokAdapter(vault=mock_vault)

    fake_creator_data = {
        "creator_nickname": "TikTokStar",
        "creator_avatar_url": "https://p16.tiktokcdn.com/avatar.jpg",
        "creator_username": "star_official",
        "max_video_post_duration_sec": 600,
    }

    with patch.object(adapter.direct_client, "query_creator_info", return_value=fake_creator_data):
        metrics = adapter.fetch_creator_metrics(profile_id=101)
        assert metrics["creator_nickname"] == "TikTokStar"
        assert metrics["creator_username"] == "star_official"
