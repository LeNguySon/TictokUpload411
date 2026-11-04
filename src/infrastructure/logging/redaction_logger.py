"""
Redaction Structured Logging System.
AgentShield Tier-1 Privacy & Anti-Leak Compliance.
"""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

REDACTION_PATTERNS = [
    # JWT tokens
    re.compile(r"eyJ[A-Za-z0-9_\-\.]{20,}", re.IGNORECASE),
    # Bearer tokens
    re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{15,}", re.IGNORECASE),
    # Passwords in URLs / queries
    re.compile(r"(password|passwd|pwd)\s*[:=]\s*[^\s&,;'\"]+", re.IGNORECASE),
    # Session cookies
    re.compile(r"(sessionid|sid_guard|msToken|odin_tt)\s*[:=]\s*[^\s&,;'\"]+", re.IGNORECASE),
    # Access and refresh tokens
    re.compile(r"(access_token|refresh_token|client_secret)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]+['\"]?", re.IGNORECASE),
]


class RedactionFilter(logging.Filter):
    """Sanitizes log messages to ensure sensitive tokens and credentials are never persisted."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self.redact(str(v)) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(self.redact(str(arg)) for arg in record.args)
        return True

    @staticmethod
    def redact(text: str) -> str:
        res = text
        for pat in REDACTION_PATTERNS:
            res = pat.sub("***REDACTED***", res)
        return res


def configure_app_logger(
    log_file: Path | str | None = None,
    level: int = logging.INFO,
    handlers: list[logging.Handler] | None = None,
) -> logging.Logger:
    """Configures root application logger with redaction filter and rotating file handlers."""
    logger = logging.getLogger("tavm")
    logger.setLevel(level)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s:%(threadName)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    redaction = RedactionFilter()

    if handlers:
        for h in handlers:
            h.setFormatter(formatter)
            h.addFilter(redaction)
            logger.addHandler(h)
    else:
        # Default Console handler
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        console.addFilter(redaction)
        logger.addHandler(console)

        # File handler if specified
        if log_file:
            p = Path(log_file)
            p.parent.mkdir(parents=True, exist_ok=True)
            file_h = RotatingFileHandler(str(p), maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
            file_h.setFormatter(formatter)
            file_h.addFilter(redaction)
            logger.addHandler(file_h)

    return logger
