"""
Unit tests validating fixes for all 9 SamMonny SDK upload defects (TAVM-2026-WIN).
Strict TDD: RED -> GREEN -> REFACTOR.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sammonny.platforms.tiktok import (
    DraftResult,
    RemoteStatus,
    TikTokHeadlessStudioUploader,
    TikTokHybridApiUploader,
    TikTokPublisherAdapter,
    UploadMode,
)


@pytest.fixture
def dummy_video(tmp_path: Path) -> Path:
    video_file = tmp_path / "sample_test_video.mp4"
    video_file.write_bytes(b"\x00" * 1024 * 50)
    return video_file


# =============================================================================
# Defect 1 & 8: Official Direct Post scheduling rejection & privacy pre-check
# =============================================================================

def test_defect_1_direct_post_rejects_schedule_time(dummy_video: Path):
    """
    Defect 1: TikTok Direct Post v2 API does not support schedule_time.
    If schedule_time is provided in DraftResult for OFFICIAL_DIRECT_POST,
    the publisher must reject or flag that local scheduling is required,
    preventing immediate accidental public posting.
    """
    adapter = TikTokPublisherAdapter()
    adapter.register_access_token("acc_1", "valid_oauth_token")

    draft = DraftResult(
        draft_id="draft_sched_1",
        file_path=str(dummy_video),
        file_size_bytes=dummy_video.stat().st_size,
        file_md5="dummy_md5",
        title="Scheduled Dance Video",
        tags=["#dance"],
        privacy="SELF_ONLY",
        schedule_time="2026-12-01 10:00:00",
    )

    with patch.object(adapter.direct_client, "query_creator_info", return_value={"privacy_level_options": ["SELF_ONLY"]}):
        result = adapter.upload(draft=draft, account_id="acc_1", preferred_mode=UploadMode.OFFICIAL_DIRECT_POST)
        # Should not succeed immediately or must fail with clear indication that Direct Post does not support remote scheduling
        assert result.success is False
        assert "schedule" in (result.error or "").lower()


def test_defect_8_direct_post_privacy_precheck_rejection(dummy_video: Path):
    """
    Defect 8: If draft requested privacy is not in creator_info allowed options
    (e.g., requested PUBLIC_TO_EVERYONE, but sandbox only allows SELF_ONLY),
    the publisher must fail fast before calling init_direct_post.
    """
    adapter = TikTokPublisherAdapter()
    adapter.register_access_token("acc_sandbox", "valid_oauth_token")

    draft = DraftResult(
        draft_id="draft_priv_1",
        file_path=str(dummy_video),
        file_size_bytes=dummy_video.stat().st_size,
        file_md5="dummy_md5",
        title="Private Video Attempt",
        tags=[],
        privacy="PUBLIC_TO_EVERYONE",
    )

    # TikTok creator info only permits SELF_ONLY for this app
    mock_info = {"privacy_level_options": ["SELF_ONLY"]}
    with patch.object(adapter.direct_client, "query_creator_info", return_value=mock_info):
        with patch.object(adapter.direct_client, "init_direct_post") as mock_init:
            result = adapter.upload(draft=draft, account_id="acc_sandbox", preferred_mode=UploadMode.OFFICIAL_DIRECT_POST)
            assert result.success is False
            assert "privacy" in (result.error or "").lower()
            mock_init.assert_not_called()


# =============================================================================
# Defect 2 & 9: DOM Privacy, Permissions (Comment, Duet, Stitch), and Scheduling
# =============================================================================

def test_defect_2_and_9_dom_studio_configures_privacy_and_permissions(dummy_video: Path):
    """
    Defects 2 & 9: upload_via_studio must configure privacy and permissions
    (allow_comment, allow_duet, allow_stitch) via CDP/DOM. Scheduling is refused up front (the page step
    never set the requested date/time): see test_dom_studio_refuses_scheduled_post.
    """
    mock_session = MagicMock()
    mock_session.profile_id = "prof_dom_1"
    mock_session.cdp = MagicMock()
    mock_session.actions = MagicMock()

    # Mock DOM node query returning a valid file input node
    mock_session.cdp.send.side_effect = lambda cmd, args=None: (
        {"root": {"nodeId": 1}} if cmd == "DOM.getDocument"
        else {"nodeId": 42} if cmd == "DOM.querySelector"
        else {}
    )

    # Mock evaluate calls
    eval_calls = []
    def mock_eval(expr: str):
        eval_calls.append(expr)
        if "captcha" in expr.lower():
            return False
        if "toggleoption" in expr.lower():
            return [True, True, True]  # comment / duet / stitch switches found and set
        if "button" in expr.lower() or "is_disabled" in expr.lower():
            return False  # not disabled
        if "confirmed" in expr.lower() or "href" in expr.lower():
            return {"confirmed": True, "publish_id": "real_studio_123"}
        return True

    mock_session.cdp.evaluate.side_effect = mock_eval

    uploader = TikTokHeadlessStudioUploader(session=mock_session)
    result = uploader.upload_via_studio(
        video_path=dummy_video,
        title="Dance Tutorial",
        tags=["#tutorial"],
        privacy="SELF_ONLY",
        allow_comment=False,
        allow_duet=False,
        allow_stitch=False,
    )

    assert result.success is True
    assert result.publish_id == "real_studio_123"

    # Verify CDP evaluate or DOM actions set privacy & permissions
    all_eval_text = " ".join(eval_calls)
    assert "privacy" in all_eval_text.lower() or mock_session.actions.click.called


def test_dom_studio_refuses_scheduled_post(dummy_video: Path):
    """The Studio page step cannot set the requested date/time: refused before touching the page."""
    mock_session = MagicMock()
    mock_session.profile_id = "prof_dom_sched"
    uploader = TikTokHeadlessStudioUploader(session=mock_session)
    result = uploader.upload_via_studio(
        video_path=dummy_video, title="Dance Tutorial", privacy="PUBLIC_TO_EVERYONE",
        schedule_time="2026-11-15 15:30:00",
    )
    assert result.success is False and result.is_ambiguous is False
    assert "schedule" in (result.error or "").lower()
    mock_session.navigate.assert_not_called()


# =============================================================================
# Defect 3: No Fake "studio_post_..." ID on unconfirmed DOM upload
# =============================================================================

def test_defect_3_dom_studio_never_returns_fake_success_id(dummy_video: Path):
    """
    Defect 3: When TikTok Studio DOM does not confirm the post,
    SDK must NOT fabricate studio_post_{timestamp} with success=True.
    It must return success=False with RemoteStatus.UNKNOWN and is_ambiguous=True.
    """
    mock_session = MagicMock()
    mock_session.profile_id = "prof_dom_2"
    mock_session.cdp = MagicMock()
    mock_session.actions = MagicMock()

    mock_session.cdp.send.side_effect = lambda cmd, args=None: (
        {"root": {"nodeId": 1}} if cmd == "DOM.getDocument"
        else {"nodeId": 42} if cmd == "DOM.querySelector"
        else {}
    )

    # Evaluate returns not disabled for Post, but NEVER returns confirmation
    def mock_eval(expr: str):
        if "disabled" in expr:
            return False
        # Confirmation check returns null/None
        return None

    mock_session.cdp.evaluate.side_effect = mock_eval

    uploader = TikTokHeadlessStudioUploader(session=mock_session)
    result = uploader.upload_via_studio(
        video_path=dummy_video,
        title="Unconfirmed Video",
    )

    assert result.success is False
    assert result.status == RemoteStatus.UNKNOWN
    assert result.is_ambiguous is True
    assert not str(result.publish_id or "").startswith("studio_post_")


# =============================================================================
# Defect 4: Hybrid Mode must NOT auto-fallback to DOM on network/V8 failure
# =============================================================================

def test_defect_4_hybrid_uploader_no_duplicate_dom_fallback(dummy_video: Path):
    """
    Defect 4: In TikTokHybridApiUploader, when V8 in-page fetch fails,
    it must NOT silently invoke upload_via_studio (which causes duplicate uploads).
    It must return success=False, is_ambiguous=True, and status=RemoteStatus.UNKNOWN.
    """
    mock_session = MagicMock()
    mock_session.profile_id = "prof_hybrid_1"
    mock_session.cdp = MagicMock()

    mock_pipeline = MagicMock()
    mock_pipeline.prepare_upload_session.return_value = {
        "upload_url": "https://tos.tiktokcdn.com/upload/mock",
        "session_id": "vod_session_888",
    }
    mock_pipeline.execute_tos_upload.return_value = {"success": True}

    uploader = TikTokHybridApiUploader(session=mock_session, pipeline=mock_pipeline)

    # Mock CDPLiveSigner returning failure/network error
    with patch("sammonny.signatures.kernel_live.CDPLiveSigner") as MockSigner:
        instance = MockSigner.return_value
        instance.execute_in_browser_fetch.return_value = {
            "status": 504,
            "status_code": 504,
            "ok": False,
            "error": "Gateway Timeout during V8 post execution",
        }

        with patch.object(TikTokHeadlessStudioUploader, "upload_via_studio") as mock_dom_fallback:
            result = uploader.upload_via_hybrid(
                video_path=dummy_video,
                title="Hybrid Risk Video",
            )

            # Must NOT call DOM fallback!
            mock_dom_fallback.assert_not_called()

            assert result.success is False
            assert result.is_ambiguous is True
            assert result.status == RemoteStatus.UNKNOWN


# =============================================================================
# Defect 5: Correct DOM Selector without :has-text() & adequate timeout
# =============================================================================

def test_defect_5_dom_selector_uses_valid_javascript(dummy_video: Path):
    """
    Defect 5: Native browser document.querySelector throws SyntaxError
    if :has-text() is used. Ensure the selector uses valid native DOM JS.
    """
    mock_session = MagicMock()
    mock_session.profile_id = "prof_dom_3"
    mock_session.cdp = MagicMock()

    evaluated_scripts = []
    def capture_eval(expr: str):
        evaluated_scripts.append(expr)
        if "captcha" in expr.lower():
            return False
        # Simulate browser throwing SyntaxError on :has-text
        if ":has-text" in expr:
            raise RuntimeError("DOMException: ':has-text' is not a valid selector.")
        if "btn" in expr or "disabled" in expr:
            return False
        return {"confirmed": True, "publish_id": "valid_post_11"}

    mock_session.cdp.evaluate.side_effect = capture_eval
    mock_session.cdp.send.return_value = {"root": {"nodeId": 1}, "nodeId": 10}

    uploader = TikTokHeadlessStudioUploader(session=mock_session)
    result = uploader.upload_via_studio(video_path=dummy_video, title="Test Valid JS")
    assert result.success is True

    # If :has-text was used in evaluate, the RuntimeError would fail or be logged
    for script in evaluated_scripts:
        assert ":has-text" not in script, f"Found invalid selector :has-text in evaluated script: {script}"


# =============================================================================
# Defect 6: Capability check does not silently swallow API error if OFFICIAL mode requested
# =============================================================================

def test_defect_6_capability_error_not_swallowed_when_official_mode_requested():
    """
    Defect 6: When query_creator_info fails and OFFICIAL_DIRECT_POST is requested,
    validate_capability must report the error rather than silently defaulting to HEADLESS_STUDIO.
    """
    mock_client = MagicMock()
    mock_client.query_creator_info.side_effect = RuntimeError("Token revoked or expired (HTTP 401)")

    adapter = TikTokPublisherAdapter(direct_client=mock_client)
    adapter.register_access_token("acc_err", "expired_token")

    cap = adapter.validate_capability("acc_err", preferred_mode=UploadMode.OFFICIAL_DIRECT_POST)

    assert cap.authorized is False or cap.mode != UploadMode.HEADLESS_STUDIO
    assert cap.error is not None
    assert "Token revoked" in cap.error or "expired" in cap.error


# =============================================================================
# Defect 7: Status reconciliation polling in SDK
# =============================================================================

def test_defect_7_reconcile_publish_polls_until_complete():
    """
    Defect 7: SDK TikTokPublisherAdapter must support reconcile_publish()
    to poll get_post_status until final confirmation (PUBLISH_COMPLETE or FAILED).
    """
    mock_client = MagicMock()
    # First 2 calls return PROCESSING_UPLOAD, 3rd returns PUBLISH_COMPLETE
    mock_client.get_post_status.side_effect = [
        {"status": "PROCESSING_UPLOAD"},
        {"status": "PROCESSING_UPLOAD"},
        {"status": "PUBLISH_COMPLETE"},
    ]

    adapter = TikTokPublisherAdapter(direct_client=mock_client)
    adapter.register_access_token("acc_rec", "valid_token")

    status = adapter.reconcile_publish(
        publish_id="v_pub_reconcile_123",
        account_id="acc_rec",
        max_attempts=5,
        poll_interval=0.01,
    )

    assert status == RemoteStatus.PUBLISH_COMPLETE
    assert mock_client.get_post_status.call_count == 3
