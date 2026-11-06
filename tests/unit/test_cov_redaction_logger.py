"""
Additional coverage tests for src/infrastructure/logging/redaction_logger.py.
Target: raise coverage from 67% to >= 85%.
Tests are hermetic: use in-memory log handlers, no real file I/O except via tmp_path.
"""

from __future__ import annotations

import io
import logging

from src.infrastructure.logging.redaction_logger import (
    RedactionFilter,
    configure_app_logger,
)

# ---------------------------------------------------------------------------
# RedactionFilter.redact — static method direct tests
# ---------------------------------------------------------------------------

class TestRedactStaticMethod:
    def test_redact_jwt_token(self):
        secret = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        result = RedactionFilter.redact(f"auth={secret}")
        assert secret not in result
        assert "***REDACTED***" in result

    def test_redact_bearer_token(self):
        secret = "BearerTokenXyz1234567890"
        result = RedactionFilter.redact(f"Authorization: Bearer {secret}")
        assert secret not in result
        assert "***REDACTED***" in result

    def test_redact_password_in_url_query(self):
        result = RedactionFilter.redact("connect?password=SuperSecret123!")
        assert "SuperSecret123!" not in result
        assert "***REDACTED***" in result

    def test_redact_passwd_variant(self):
        result = RedactionFilter.redact("auth passwd=hunter2")
        assert "hunter2" not in result

    def test_redact_pwd_variant(self):
        result = RedactionFilter.redact("params: pwd=abc123")
        assert "abc123" not in result

    def test_redact_session_cookie_sessionid(self):
        result = RedactionFilter.redact("cookie: sessionid=ABCDEF1234567890")
        assert "ABCDEF1234567890" not in result
        assert "***REDACTED***" in result

    def test_redact_session_cookie_sid_guard(self):
        result = RedactionFilter.redact("sid_guard=XYZABC123")
        assert "XYZABC123" not in result

    def test_redact_session_cookie_msToken(self):
        result = RedactionFilter.redact("msToken=token_value_here")
        assert "token_value_here" not in result

    def test_redact_session_cookie_odin_tt(self):
        result = RedactionFilter.redact("odin_tt=some_session_value")
        assert "some_session_value" not in result

    def test_redact_access_token_key(self):
        result = RedactionFilter.redact("access_token=fake-at-secret-abc123")
        assert "fake-at-secret-abc123" not in result
        assert "***REDACTED***" in result

    def test_redact_refresh_token_key(self):
        result = RedactionFilter.redact("refresh_token='fake-rt-xyz'")
        assert "fake-rt-xyz" not in result

    def test_redact_client_secret_key(self):
        result = RedactionFilter.redact('client_secret="fake-cs-abc"')
        assert "fake-cs-abc" not in result

    def test_redact_proxy_credentials_in_url(self):
        url = "http://proxyuser:fake-proxy-password@proxy.example.com:3128"
        result = RedactionFilter.redact(url)
        assert "fake-proxy-password" not in result
        assert "***REDACTED***" in result

    def test_redact_safe_text_unchanged(self):
        safe = "Profile 42 uploaded video.mp4 successfully."
        assert RedactionFilter.redact(safe) == safe

    def test_redact_multiple_secrets_in_one_message(self):
        msg = "access_token=fake-at Bearer fake-bearer-token-longxxx sessionid=sid123"
        result = RedactionFilter.redact(msg)
        assert "fake-at" not in result
        assert "fake-bearer-token-longxxx" not in result
        assert "sid123" not in result


# ---------------------------------------------------------------------------
# RedactionFilter.filter — LogRecord manipulation
# ---------------------------------------------------------------------------

class TestRedactionFilterRecord:
    def _make_record(self, msg: str, args=None) -> logging.LogRecord:
        """Build a LogRecord without triggering the Python 3.11 Mapping-index bug.

        Python 3.11's LogRecord.__init__ does ``args[0]`` to detect a sole-dict arg,
        which raises KeyError if args *is* a dict (not a 1-tuple wrapping a dict).
        We work around this by constructing with a tuple and then patching .args directly.
        """
        r = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname=__file__, lineno=0,
            msg=msg, args=(), exc_info=None,
        )
        if args is not None:
            r.args = args
        return r

    def test_filter_string_msg_redacted(self):
        flt = RedactionFilter()
        r = self._make_record("Token access_token=fake-secret-123")
        flt.filter(r)
        assert "fake-secret-123" not in r.msg
        assert "***REDACTED***" in r.msg

    def test_filter_non_string_msg_untouched(self):
        """Non-string messages (e.g. dict) must pass through unchanged."""
        flt = RedactionFilter()
        r = self._make_record("placeholder")
        r.msg = {"key": "value"}
        flt.filter(r)
        assert r.msg == {"key": "value"}

    def test_filter_tuple_args_redacted(self):
        flt = RedactionFilter()
        r = self._make_record("msg %s %s", args=("access_token=fake-at-tuple", "plain"))
        flt.filter(r)
        assert isinstance(r.args, tuple)
        assert "fake-at-tuple" not in r.args[0]
        assert r.args[1] == "plain"

    def test_filter_tuple_args_non_string_preserved(self):
        flt = RedactionFilter()
        r = self._make_record("val=%d", args=(42,))
        flt.filter(r)
        assert r.args == (42,)

    def test_filter_dict_args_redacted(self):
        flt = RedactionFilter()
        r = self._make_record("%(token)s", args={"token": "access_token=fake-dict-token"})
        flt.filter(r)
        assert isinstance(r.args, dict)
        assert "fake-dict-token" not in r.args["token"]

    def test_filter_dict_args_non_string_preserved(self):
        flt = RedactionFilter()
        r = self._make_record("%(count)d", args={"count": 99})
        flt.filter(r)
        assert r.args["count"] == 99

    def test_filter_always_returns_true(self):
        flt = RedactionFilter()
        r = self._make_record("some message")
        assert flt.filter(r) is True

    def test_filter_empty_args_tuple(self):
        flt = RedactionFilter()
        r = self._make_record("plain message", args=())
        flt.filter(r)
        assert r.args == ()


# ---------------------------------------------------------------------------
# configure_app_logger
# ---------------------------------------------------------------------------

class TestConfigureAppLogger:
    def test_returns_logger_named_tavm(self):
        buf = io.StringIO()
        h = logging.StreamHandler(buf)
        lgr = configure_app_logger(handlers=[h])
        assert lgr.name == "tavm"

    def test_custom_level_applied(self):
        buf = io.StringIO()
        h = logging.StreamHandler(buf)
        lgr = configure_app_logger(handlers=[h], level=logging.DEBUG)
        assert lgr.level == logging.DEBUG

    def test_default_console_handler_added_when_no_handlers(self):
        lgr = configure_app_logger()
        assert len(lgr.handlers) >= 1

    def test_no_secrets_in_console_output(self):
        buf = io.StringIO()
        h = logging.StreamHandler(buf)
        lgr = configure_app_logger(handlers=[h])
        lgr.info("access_token=fake-at-console-test")
        output = buf.getvalue()
        assert "fake-at-console-test" not in output
        assert "***REDACTED***" in output

    def test_logger_clears_previous_handlers_on_reconfigure(self):
        """Calling configure_app_logger twice must not accumulate handlers."""
        lgr = configure_app_logger()
        count_first = len(lgr.handlers)
        configure_app_logger()
        assert len(lgr.handlers) == count_first

    def test_file_handler_created_when_log_file_given(self, tmp_path):
        log_path = tmp_path / "sub" / "app.log"
        lgr = configure_app_logger(log_file=log_path)
        # Must have both console + file handler
        assert len(lgr.handlers) == 2
        lgr.info("access_token=fake-at-file-test")
        for h in lgr.handlers:
            h.flush()
        assert log_path.exists()
        content = log_path.read_text(encoding="utf-8")
        assert "fake-at-file-test" not in content
        assert "***REDACTED***" in content
        # Cleanup handlers to avoid file lock issues on Windows
        for h in list(lgr.handlers):
            h.close()
            lgr.removeHandler(h)

    def test_no_secrets_logged_through_logger(self):
        buf = io.StringIO()
        h = logging.StreamHandler(buf)
        lgr = configure_app_logger(handlers=[h])
        lgr.warning("proxy=http://user:fake-proxy-secret@proxy.example.com:3128")
        output = buf.getvalue()
        assert "fake-proxy-secret" not in output

    def test_redaction_patterns_cover_all_critical_types(self):
        """Smoke-check that all REDACTION_PATTERNS compile and match their targets."""
        test_cases = [
            ("http://user:secret@host", "secret"),
            ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9abcdef12345678901234", "eyJhbGciOi"),
            ("Bearer fake-bearer-token-longlong", "fake-bearer-token-longlong"),
            ("password=hunter2", "hunter2"),
            ("sessionid=sid_value_12345", "sid_value_12345"),
            ("access_token=fake-access-123", "fake-access-123"),
        ]
        for text, secret in test_cases:
            result = RedactionFilter.redact(text)
            assert secret not in result, f"Pattern failed to redact: {secret!r} in {text!r}"
