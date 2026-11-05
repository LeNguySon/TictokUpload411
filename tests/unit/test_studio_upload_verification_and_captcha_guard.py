"""
Unit tests for TikTokHeadlessStudioUploader Verification & Captcha Guard.
Tests:
1. File input missing -> FAILED (No false positive)
2. SecSDK Captcha present -> MANUAL_REQUIRED (Suspends execution safely)
3. Post button disabled -> FAILED
4. Authentic DOM success confirmation -> PUBLISH_COMPLETE
5. DOM error toast detection -> FAILED
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sammonny import RemoteStatus
from sammonny.platforms.tiktok import TikTokHeadlessStudioUploader


@pytest.fixture
def dummy_video(tmp_path: Path) -> Path:
    vid = tmp_path / "studio_test.mp4"
    vid.write_bytes(b"dummy video data 1234567890")
    return vid


def test_studio_upload_fails_when_file_input_missing(dummy_video: Path) -> None:
    """Verifies upload fails cleanly instead of returning fake success when file input is not found."""
    mock_session = MagicMock()
    mock_session.profile_id = "test_prof_1"
    mock_session.cdp.send.side_effect = lambda method, params=None: (
        {"root": {"nodeId": 1}} if method == "DOM.getDocument" else {"nodeId": 0}
    )
    mock_session.cdp.evaluate.return_value = False

    uploader = TikTokHeadlessStudioUploader(mock_session)
    result = uploader.upload_via_studio(dummy_video, title="Test Video")

    assert result.success is False
    assert result.status == RemoteStatus.FAILED
    assert "input" in result.error.lower()


def test_studio_upload_halts_safely_when_captcha_detected(dummy_video: Path) -> None:
    """Verifies upload halts immediately with MANUAL_REQUIRED when SecSDK Captcha is active."""
    mock_session = MagicMock()
    mock_session.profile_id = "test_prof_1"

    # Captcha present expression evaluation
    def evaluate_side_effect(expr: str):
        if "captcha" in expr.lower():
            return True
        return False

    mock_session.cdp.evaluate.side_effect = evaluate_side_effect
    uploader = TikTokHeadlessStudioUploader(mock_session)

    result = uploader.upload_via_studio(dummy_video, title="Test Captcha Video")

    assert result.success is False
    assert result.status == RemoteStatus.MANUAL_REQUIRED
    assert "captcha" in result.error.lower()
    # Must NEVER have called actions.click to blindly click Post during captcha
    mock_session.actions.click.assert_not_called()


def test_studio_upload_fails_when_post_button_disabled(dummy_video: Path) -> None:
    """Verifies upload fails when post button remains disabled instead of falsely succeeding."""
    mock_session = MagicMock()
    mock_session.profile_id = "test_prof_1"

    # File input found
    mock_session.cdp.send.side_effect = lambda method, params=None: (
        {"root": {"nodeId": 1}} if method == "DOM.getDocument" else {"nodeId": 999}
    )

    # Captcha clean, but post button is disabled (returns True for is_disabled)
    def evaluate_side_effect(expr: str):
        if "captcha" in expr.lower():
            return False
        if "disabled" in expr.lower():
            return True
        return None

    mock_session.cdp.evaluate.side_effect = evaluate_side_effect
    uploader = TikTokHeadlessStudioUploader(mock_session)

    result = uploader.upload_via_studio(dummy_video, title="Test Disabled Button")

    assert result.success is False
    assert result.status == RemoteStatus.FAILED
    assert "post button" in result.error.lower() or "disabled" in result.error.lower()


def test_studio_upload_verifies_authentic_dom_success(dummy_video: Path) -> None:
    """Verifies upload marks PUBLISH_COMPLETE only when authentic DOM confirmation is observed."""
    mock_session = MagicMock()
    mock_session.profile_id = "test_prof_1"

    # File input found
    mock_session.cdp.send.side_effect = lambda method, params=None: (
        {"root": {"nodeId": 1}} if method == "DOM.getDocument" else {"nodeId": 999}
    )

    # Post ready, and post confirmation received
    def evaluate_side_effect(expr: str):
        if "captcha" in expr.lower():
            return False
        if "disabled" in expr.lower():
            return False  # Button is ready
        if "confirm" in expr.lower() or "upload" in expr.lower():
            return {"confirmed": True, "publish_id": "7392819284"}
        return None

    mock_session.cdp.evaluate.side_effect = evaluate_side_effect
    uploader = TikTokHeadlessStudioUploader(mock_session)

    result = uploader.upload_via_studio(dummy_video, title="Test Authentic Success")

    assert result.success is True
    assert result.status == RemoteStatus.PUBLISH_COMPLETE
    assert result.publish_id is not None


def test_studio_upload_catches_tiktok_error_toast(dummy_video: Path) -> None:
    """Verifies upload fails and reports reason when TikTok displays an error toast."""
    mock_session = MagicMock()
    mock_session.profile_id = "test_prof_1"

    mock_session.cdp.send.side_effect = lambda method, params=None: (
        {"root": {"nodeId": 1}} if method == "DOM.getDocument" else {"nodeId": 999}
    )

    def evaluate_side_effect(expr: str):
        if "captcha" in expr.lower():
            return False
        if "disabled" in expr.lower():
            return False
        if "confirm" in expr.lower() or "toast" in expr.lower() or "upload" in expr.lower():
            return {"error": "Video violates community guidelines"}
        return None

    mock_session.cdp.evaluate.side_effect = evaluate_side_effect
    uploader = TikTokHeadlessStudioUploader(mock_session)

    result = uploader.upload_via_studio(dummy_video, title="Test Error Toast")

    assert result.success is False
    assert result.status == RemoteStatus.FAILED
    assert "guidelines" in result.error.lower()
