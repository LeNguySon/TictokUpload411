"""
Unit tests for Domain Policies: NetworkLeakPolicy, VideoValidationPolicy, RetryPolicy.
Strict TDD - Phase 2 (RED)
"""

import tempfile
from pathlib import Path

from src.domain.policies.network_leak_policy import NetworkLeakPolicy
from src.domain.policies.retry_policy import ErrorClassification, RetryPolicy
from src.domain.policies.video_validation_policy import VideoValidationPolicy


def test_network_leak_policy_detects_leak():
    policy = NetworkLeakPolicy(known_host_ips={"113.190.23.45", "127.0.0.1"})

    # Case 1: Egress IP matches local machine IP -> LEAK DETECTED!
    report = policy.evaluate(proxy_egress_ip="113.190.23.45")
    assert report.is_safe is False
    assert report.leak_detected is True
    assert "Critical IP Leak" in report.reason

    # Case 2: Egress IP is different from host IP -> SAFE
    safe_report = policy.evaluate(proxy_egress_ip="142.250.190.46")
    assert safe_report.is_safe is True
    assert safe_report.leak_detected is False


def test_video_validation_policy():
    policy = VideoValidationPolicy(
        min_size_bytes=1024,
        max_size_bytes=500 * 1024 * 1024,  # 500MB
        min_duration_sec=3.0,
        max_duration_sec=600.0,
        allowed_extensions={".mp4", ".mov", ".webm"},
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # 1. Non-existent file
        res = policy.validate_file(tmp_path / "missing.mp4")
        assert res.is_valid is False
        assert "not found" in res.error_message.lower()

        # 2. Unsupported extension
        txt_file = tmp_path / "sample.txt"
        txt_file.write_text("dummy")
        res = policy.validate_file(txt_file)
        assert res.is_valid is False
        assert "unsupported file format" in res.error_message.lower()

        # 3. File too small (0 bytes)
        empty_mp4 = tmp_path / "empty.mp4"
        empty_mp4.touch()
        res = policy.validate_file(empty_mp4)
        assert res.is_valid is False
        assert "too small" in res.error_message.lower()

        # 4. Valid file
        valid_mp4 = tmp_path / "valid.mp4"
        valid_mp4.write_bytes(b"\x00" * 4096)
        res = policy.validate_file(valid_mp4, duration_sec=15.0)
        assert res.is_valid is True

        # 5. Duration exceeding limit
        res_long = policy.validate_file(valid_mp4, duration_sec=700.0)
        assert res_long.is_valid is False
        assert "duration" in res_long.error_message.lower()


def test_retry_policy_classification_and_backoff():
    policy = RetryPolicy(max_retries=3, base_delay_sec=1.0, max_delay_sec=10.0)

    # 1. Non-retryable error: Token revoked or Account banned
    cat_401 = policy.classify_error("HTTP 401 Unauthorized: token expired")
    assert cat_401 == ErrorClassification.NON_RETRYABLE_AUTH
    assert policy.should_retry(attempt=0, error="HTTP 401 Unauthorized") is False

    cat_die = policy.classify_error("Account is CHECKPOINT or banned")
    assert cat_die == ErrorClassification.NON_RETRYABLE_ACCOUNT
    assert policy.should_retry(attempt=0, error="Account is CHECKPOINT") is False

    # 2. Retryable error: HTTP 429 Rate Limit or 504 Gateway Timeout
    cat_429 = policy.classify_error("HTTP 429 Too Many Requests")
    assert cat_429 == ErrorClassification.RETRYABLE_NETWORK
    assert policy.should_retry(attempt=1, error="HTTP 429 Too Many Requests") is True
    assert policy.should_retry(attempt=3, error="HTTP 429 Too Many Requests") is False  # Exceeded max_retries

    # 3. Delay calculation
    delay_0 = policy.get_delay_seconds(attempt=0)
    assert 1.0 <= delay_0 <= 2.5
    delay_1 = policy.get_delay_seconds(attempt=1)
    assert delay_1 >= delay_0
