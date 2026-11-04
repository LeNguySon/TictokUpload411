"""
Unit tests for Redaction Structured Logger (AgentShield Tier-1 Privacy).
"""

import io
import logging

from src.infrastructure.logging.redaction_logger import (
    RedactionFilter,
    configure_app_logger,
)


def test_redaction_filter_replaces_sensitive_data():
    flt = RedactionFilter()

    # Create test record
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Connecting with Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9 and sessionid=a1b2c3d4e5f6g7h8 and password=SuperSecret123!",
        args=(),
        exc_info=None,
    )

    flt.filter(record)

    assert "SuperSecret123!" not in record.msg
    assert "eyJhbGciOi" not in record.msg
    assert "a1b2c3d4e5f6g7h8" not in record.msg
    assert "***REDACTED***" in record.msg


def test_logger_structured_output():
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    logger = configure_app_logger(handlers=[handler])

    logger.info("Syncing profile 10 with access_token: secret_act_token_123")

    output = log_stream.getvalue()
    assert "secret_act_token_123" not in output
    assert "***REDACTED***" in output
