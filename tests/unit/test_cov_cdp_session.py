"""
Additional coverage tests for src/infrastructure/browser/cdp_session.py.
Target: raise coverage from 57% to >= 85%.
Tests are hermetic: urllib.request and websockets are mocked — no real browser or network.
"""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest
from src.infrastructure.browser.cdp_session import (
    CdpError,
    _http_base,
    cdp_call,
    fetch_tiktok_cookies,
    open_url,
    summarize_tiktok_cookies,
)

# ---------------------------------------------------------------------------
# _http_base — URL normalization
# ---------------------------------------------------------------------------

class TestHttpBase:
    def test_bare_host_port(self):
        assert _http_base("localhost:9222") == "http://localhost:9222"

    def test_http_prefix_stripped(self):
        assert _http_base("http://127.0.0.1:9222") == "http://127.0.0.1:9222"

    def test_https_prefix_stripped(self):
        assert _http_base("https://127.0.0.1:9222") == "http://127.0.0.1:9222"

    def test_ws_prefix_stripped(self):
        assert _http_base("ws://127.0.0.1:9222") == "http://127.0.0.1:9222"

    def test_wss_prefix_stripped(self):
        assert _http_base("wss://127.0.0.1:9222") == "http://127.0.0.1:9222"

    def test_path_after_host_stripped(self):
        # Only the host:port portion should remain
        result = _http_base("127.0.0.1:9222/devtools/browser/uuid")
        assert result == "http://127.0.0.1:9222"

    def test_whitespace_stripped(self):
        result = _http_base("  localhost:9222  ")
        assert result == "http://localhost:9222"


# ---------------------------------------------------------------------------
# cdp_call — success path
# ---------------------------------------------------------------------------

class TestCdpCall:
    def _make_ws_resp(self, payload: dict) -> MagicMock:
        """Build a mock websocket that returns a single message then blocks."""
        ws = MagicMock()
        ws.send = MagicMock()
        ws.recv = MagicMock(return_value=json.dumps(payload))
        ws.__enter__ = lambda s: s
        ws.__exit__ = MagicMock(return_value=False)
        return ws

    def _mock_urlopen(self, ws_url: str = "ws://localhost:9222/devtools/browser/fake-id"):
        resp = MagicMock()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        resp.read.return_value = json.dumps({"webSocketDebuggerUrl": ws_url}).encode()
        return resp

    def test_success_returns_result(self):
        ws = self._make_ws_resp({"id": 1, "result": {"cookies": []}})
        url_resp = self._mock_urlopen()

        with (
            patch("urllib.request.urlopen", return_value=url_resp),
            patch("websockets.sync.client.connect", return_value=ws),
        ):
            result = cdp_call("localhost:9222", "Storage.getCookies")
        assert result == {"cookies": []}

    def test_cdp_error_raises_CdpError(self):
        ws = self._make_ws_resp({"id": 1, "error": {"message": "Target closed"}})
        url_resp = self._mock_urlopen()

        with (
            patch("urllib.request.urlopen", return_value=url_resp),
            patch("websockets.sync.client.connect", return_value=ws),
        ):
            with pytest.raises(CdpError, match="Target closed"):
                cdp_call("localhost:9222", "Target.activateTarget")

    def test_cdp_error_without_message_key(self):
        """Error dict without 'message' should still raise CdpError."""
        ws = self._make_ws_resp({"id": 1, "error": {"code": -32601}})
        url_resp = self._mock_urlopen()

        with (
            patch("urllib.request.urlopen", return_value=url_resp),
            patch("websockets.sync.client.connect", return_value=ws),
        ):
            with pytest.raises(CdpError):
                cdp_call("localhost:9222", "Unknown.Method")

    def test_timeout_raises_CdpError_when_no_matching_id(self):
        """If no message with matching id arrives before deadline, CdpError raised."""
        ws = MagicMock()
        ws.send = MagicMock()
        # Always return messages with wrong id
        ws.recv = MagicMock(return_value=json.dumps({"id": 99, "result": {}}))
        ws.__enter__ = lambda s: s
        ws.__exit__ = MagicMock(return_value=False)
        url_resp = self._mock_urlopen()

        with (
            patch("urllib.request.urlopen", return_value=url_resp),
            patch("websockets.sync.client.connect", return_value=ws),
            patch("time.monotonic", side_effect=[0.0, 0.0, 999.0, 999.0]),
        ):
            with pytest.raises(CdpError, match="No DevTools reply"):
                cdp_call("localhost:9222", "Some.Method", timeout=1.0)

    def test_passes_params_in_request(self):
        ws = self._make_ws_resp({"id": 1, "result": {}})
        url_resp = self._mock_urlopen()
        sent_messages = []

        def capture_send(msg):
            sent_messages.append(json.loads(msg))

        ws.send = capture_send

        with (
            patch("urllib.request.urlopen", return_value=url_resp),
            patch("websockets.sync.client.connect", return_value=ws),
        ):
            cdp_call("localhost:9222", "Target.createTarget", {"url": "https://tiktok.com"})

        assert len(sent_messages) == 1
        assert sent_messages[0]["method"] == "Target.createTarget"
        assert sent_messages[0]["params"]["url"] == "https://tiktok.com"

    def test_empty_result_returns_empty_dict(self):
        """When result key is absent, should return empty dict."""
        ws = self._make_ws_resp({"id": 1})
        url_resp = self._mock_urlopen()

        with (
            patch("urllib.request.urlopen", return_value=url_resp),
            patch("websockets.sync.client.connect", return_value=ws),
        ):
            result = cdp_call("localhost:9222", "Runtime.evaluate")
        assert result == {}


# ---------------------------------------------------------------------------
# fetch_tiktok_cookies
# ---------------------------------------------------------------------------

class TestFetchTiktokCookies:
    def _cdp_mock(self, cookies: list) -> MagicMock:
        m = MagicMock(return_value={"cookies": cookies})
        return m

    def test_returns_only_tiktok_cookies(self):
        all_cookies = [
            {"name": "sessionid", "domain": ".tiktok.com", "value": "fakesid"},
            {"name": "other", "domain": ".google.com", "value": "nope"},
            {"name": "tt_webid", "domain": "www.tiktok.com", "value": "fakewebid"},
        ]
        with patch(
            "src.infrastructure.browser.cdp_session.cdp_call",
            return_value={"cookies": all_cookies},
        ):
            result = fetch_tiktok_cookies("localhost:9222")
        domains = [c["domain"].lstrip(".") for c in result]
        assert all(d.endswith("tiktok.com") for d in domains)
        assert len(result) == 2

    def test_returns_empty_when_no_cookies(self):
        with patch(
            "src.infrastructure.browser.cdp_session.cdp_call",
            return_value={"cookies": []},
        ):
            result = fetch_tiktok_cookies("localhost:9222")
        assert result == []

    def test_handles_missing_cookies_key(self):
        with patch(
            "src.infrastructure.browser.cdp_session.cdp_call",
            return_value={},
        ):
            result = fetch_tiktok_cookies("localhost:9222")
        assert result == []


# ---------------------------------------------------------------------------
# open_url
# ---------------------------------------------------------------------------

def test_open_url_calls_cdp_create_target():
    with patch("src.infrastructure.browser.cdp_session.cdp_call") as mock_cdp:
        open_url("localhost:9222", "https://www.tiktok.com/")
    mock_cdp.assert_called_once_with(
        "localhost:9222", "Target.createTarget", {"url": "https://www.tiktok.com/"}
    )


# ---------------------------------------------------------------------------
# summarize_tiktok_cookies
# ---------------------------------------------------------------------------

class TestSummarizeTiktokCookies:
    _NOW = 1_700_000_000.0  # fixed reference time

    def _cookie(self, name: str, value: str, domain: str = ".tiktok.com", expires: float = -1) -> dict:
        return {"name": name, "domain": domain, "value": value, "expires": expires}

    def test_basic_summary(self):
        cookies = [
            self._cookie("sessionid", "fakesid", expires=self._NOW + 3600),
            self._cookie("tt_webid", "fakewebid"),
        ]
        summary, expiry = summarize_tiktok_cookies(cookies, now=self._NOW)
        assert "sessionid=fakesid" in summary
        assert "tt_webid=fakewebid" in summary
        assert expiry == pytest.approx(self._NOW + 3600)

    def test_expired_cookie_excluded(self):
        cookies = [
            self._cookie("sessionid", "fakesid", expires=self._NOW - 1),
        ]
        summary, expiry = summarize_tiktok_cookies(cookies, now=self._NOW)
        assert "sessionid" not in summary
        assert expiry is None

    def test_non_tiktok_domain_excluded(self):
        cookies = [
            self._cookie("other", "value", domain=".google.com"),
        ]
        summary, expiry = summarize_tiktok_cookies(cookies, now=self._NOW)
        assert "other" not in summary

    def test_empty_name_excluded(self):
        cookies = [{"name": "", "domain": ".tiktok.com", "value": "v", "expires": -1}]
        summary, expiry = summarize_tiktok_cookies(cookies, now=self._NOW)
        assert summary == ""

    def test_session_expiry_uses_max(self):
        cookies = [
            self._cookie("sessionid", "s1", expires=self._NOW + 100),
            self._cookie("sessionid_ss", "s2", expires=self._NOW + 200),
        ]
        _, expiry = summarize_tiktok_cookies(cookies, now=self._NOW)
        assert expiry == pytest.approx(self._NOW + 200)

    def test_no_session_cookie_expiry_is_none(self):
        cookies = [
            self._cookie("tt_webid", "fakewebid"),
        ]
        _, expiry = summarize_tiktok_cookies(cookies, now=self._NOW)
        assert expiry is None

    def test_now_defaults_to_current_time(self):
        """Call without 'now' must not raise."""
        cookies = [self._cookie("sessionid", "fakesid", expires=time.time() + 3600)]
        summary, expiry = summarize_tiktok_cookies(cookies)
        assert "sessionid=fakesid" in summary

    def test_duplicate_name_uses_first_occurrence(self):
        """setdefault must keep the first value."""
        cookies = [
            self._cookie("tt_webid", "first_value"),
            self._cookie("tt_webid", "second_value"),
        ]
        summary, _ = summarize_tiktok_cookies(cookies, now=self._NOW)
        assert "first_value" in summary
        assert "second_value" not in summary

    def test_zero_expires_treated_as_session_cookie(self):
        """expires=0 means session cookie (should not be excluded as expired)."""
        cookies = [
            self._cookie("sessionid", "fakesid", expires=0),
        ]
        summary, expiry = summarize_tiktok_cookies(cookies, now=self._NOW)
        # expires=0 means -1<0<=now is False, so not excluded
        assert "sessionid=fakesid" in summary
        # expires=0 -> session_expiry condition: 0>0 is False -> no expiry set
        assert expiry is None
