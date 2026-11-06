"""
Additional coverage tests for src/domain/policies/network_leak_policy.py.
Target: raise coverage from 67% to >= 85%.
Tests are hermetic: socket, urllib, and time are mocked.
The global conftest.py already monkeypatches discover_public_ip -> None for most tests.
Tests that need specific discover_public_ip behavior override it locally.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from src.domain.policies.network_leak_policy import (
    _PUBLIC_IP_CACHE,
    _PUBLIC_IP_TTL_S,
    LeakAuditResult,
    NetworkLeakPolicy,
    discover_public_ip,
)

# ---------------------------------------------------------------------------
# LeakAuditResult dataclass
# ---------------------------------------------------------------------------

class TestLeakAuditResult:
    def test_frozen_dataclass_fields(self):
        r = LeakAuditResult(is_safe=True, leak_detected=False, egress_ip="1.2.3.4", reason="ok")
        assert r.is_safe is True
        assert r.leak_detected is False
        assert r.egress_ip == "1.2.3.4"
        assert r.reason == "ok"

    def test_frozen_cannot_assign(self):
        r = LeakAuditResult(is_safe=False, leak_detected=True, egress_ip="5.5.5.5", reason="leak")
        with pytest.raises((AttributeError, TypeError)):
            r.is_safe = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# discover_public_ip
# ---------------------------------------------------------------------------

class TestDiscoverPublicIp:
    def setup_method(self):
        """Clear the module-level cache before each test."""
        _PUBLIC_IP_CACHE.clear()

    def test_returns_ip_from_first_service(self):
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = b"203.0.113.1"

        with (
            patch("urllib.request.urlopen", return_value=mock_resp),
            patch("socket.inet_pton"),
        ):
            ip = discover_public_ip(timeout=1.0)
        assert ip == "203.0.113.1"

    def test_returns_cached_value_within_ttl(self):
        _PUBLIC_IP_CACHE["ip"] = (time.monotonic(), "10.0.0.1")
        # With a valid cache entry, no network call should be made
        with patch("urllib.request.urlopen", side_effect=Exception("should not be called")):
            ip = discover_public_ip()
        assert ip == "10.0.0.1"

    def test_refreshes_after_ttl_expires(self):
        # Plant an expired cache entry
        _PUBLIC_IP_CACHE["ip"] = (time.monotonic() - _PUBLIC_IP_TTL_S - 1, "10.0.0.1")

        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = b"203.0.113.2"

        with (
            patch("urllib.request.urlopen", return_value=mock_resp),
            patch("socket.inet_pton"),
        ):
            ip = discover_public_ip()
        assert ip == "203.0.113.2"

    def test_returns_none_when_all_services_fail(self):
        _PUBLIC_IP_CACHE.clear()
        with patch("urllib.request.urlopen", side_effect=OSError("network error")):
            ip = discover_public_ip(timeout=0.01)
        assert ip is None

    def test_skips_service_on_invalid_ip_format(self):
        """If inet_pton raises, service is skipped, next service tried."""
        _PUBLIC_IP_CACHE.clear()
        call_count = 0
        good_resp = MagicMock()
        good_resp.__enter__ = lambda s: s
        good_resp.__exit__ = MagicMock(return_value=False)
        good_resp.read.return_value = b"203.0.113.3"

        def mock_urlopen(req, timeout=5.0):
            nonlocal call_count
            call_count += 1
            return good_resp

        def mock_inet_pton(family, text):
            if call_count == 1:
                raise OSError("invalid ip on first call")
            # second call succeeds

        with (
            patch("urllib.request.urlopen", side_effect=mock_urlopen),
            patch("socket.inet_pton", side_effect=mock_inet_pton),
        ):
            ip = discover_public_ip()
        assert ip == "203.0.113.3"
        assert call_count >= 2


# ---------------------------------------------------------------------------
# NetworkLeakPolicy — constructor
# ---------------------------------------------------------------------------

class TestNetworkLeakPolicyConstructor:
    def test_with_known_host_ips_does_not_discover_local(self):
        """When known_host_ips is provided, _needs_public_ip must be False and no socket call."""
        with patch("socket.gethostname", side_effect=Exception("must not be called")):
            policy = NetworkLeakPolicy(known_host_ips={"192.168.1.1"})
        assert "192.168.1.1" in policy.known_host_ips
        assert policy._needs_public_ip is False

    def test_without_known_host_ips_discovers_local(self):
        """When no known_host_ips provided, loopback addresses must always be in the set."""
        policy = NetworkLeakPolicy()
        assert "127.0.0.1" in policy.known_host_ips

    def test_discover_local_ips_handles_socket_error(self):
        """_discover_local_ips must still return loopback when gethostname/getaddrinfo fails."""
        with (
            patch("socket.gethostname", side_effect=OSError("hostname error")),
        ):
            ips = NetworkLeakPolicy._discover_local_ips()
        assert "127.0.0.1" in ips
        assert "::1" in ips


# ---------------------------------------------------------------------------
# NetworkLeakPolicy.evaluate
# ---------------------------------------------------------------------------

class TestNetworkLeakPolicyEvaluate:
    def test_evaluate_none_egress_is_unsafe_no_leak(self):
        policy = NetworkLeakPolicy(known_host_ips={"1.2.3.4"})
        result = policy.evaluate(None)
        assert result.is_safe is False
        assert result.leak_detected is False
        assert result.egress_ip is None
        assert "Unable to determine" in result.reason

    def test_evaluate_safe_ip(self):
        policy = NetworkLeakPolicy(known_host_ips={"192.168.1.1"})
        result = policy.evaluate("8.8.8.8")
        assert result.is_safe is True
        assert result.leak_detected is False
        assert result.egress_ip == "8.8.8.8"

    def test_evaluate_leak_detected(self):
        policy = NetworkLeakPolicy(known_host_ips={"203.0.113.42"})
        result = policy.evaluate("203.0.113.42")
        assert result.is_safe is False
        assert result.leak_detected is True
        assert "203.0.113.42" in result.reason

    def test_evaluate_strips_whitespace_from_egress_ip(self):
        policy = NetworkLeakPolicy(known_host_ips={"1.2.3.4"})
        result = policy.evaluate("  1.2.3.4  ")
        assert result.leak_detected is True
        assert result.egress_ip == "1.2.3.4"

    def test_evaluate_needs_public_ip_adds_it_to_known_set(self):
        """When _needs_public_ip=True and discover_public_ip returns an IP,
        it should be added to known_host_ips and evaluated."""
        policy = NetworkLeakPolicy()  # no known_host_ips -> _needs_public_ip = True
        assert policy._needs_public_ip is True

        discovered_ip = "77.88.99.11"
        with patch(
            "src.domain.policies.network_leak_policy.discover_public_ip",
            return_value=discovered_ip,
        ):
            result = policy.evaluate(discovered_ip)  # egress = our public IP -> leak

        assert result.leak_detected is True
        assert discovered_ip in policy.known_host_ips
        assert policy._needs_public_ip is False

    def test_evaluate_needs_public_ip_no_public_found(self):
        """When discover_public_ip returns None, evaluation still proceeds."""
        policy = NetworkLeakPolicy()
        policy.known_host_ips = {"127.0.0.1", "::1"}
        policy._needs_public_ip = True

        with patch(
            "src.domain.policies.network_leak_policy.discover_public_ip",
            return_value=None,
        ):
            result = policy.evaluate("8.8.8.8")

        assert result.is_safe is True
        assert policy._needs_public_ip is False

    def test_evaluate_needs_public_ip_only_called_once(self):
        """After the first evaluate(), _needs_public_ip is False — subsequent calls skip it."""
        policy = NetworkLeakPolicy(known_host_ips={"1.1.1.1"})
        policy._needs_public_ip = True

        with patch(
            "src.domain.policies.network_leak_policy.discover_public_ip",
            return_value="5.5.5.5",
        ) as mock_discover:
            policy.evaluate("2.2.2.2")
            policy.evaluate("3.3.3.3")

        mock_discover.assert_called_once()

    def test_evaluate_loopback_is_always_in_known_set(self):
        policy = NetworkLeakPolicy()
        result = policy.evaluate("127.0.0.1")
        assert result.leak_detected is True
