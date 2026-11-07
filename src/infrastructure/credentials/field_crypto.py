"""
At-rest protection of secret DB fields with Windows DPAPI (CurrentUser scope).

Cookies reach 16 KB, beyond Windows Credential Manager's ~2.5 KB blob limit, so secrets stay in SQLite but
encrypted per value: ``dpapi:v1:<base64>``. Only the same Windows user on the same machine can decrypt them.

- ``protect`` is idempotent (already protected values are returned unchanged) and keeps None/"" as is.
- ``reveal`` passes legacy plaintext through, so pre-migration rows keep working; a value that cannot be
  decrypted (DB copied from another machine/user) reads as "" instead of raising.
AgentShield: no value is ever logged.
"""

from __future__ import annotations

import base64
import logging
from collections.abc import Mapping
from typing import Any

logger = logging.getLogger(__name__)

PREFIX = "dpapi:v1:"
_ENTROPY = b"TAVM.secret-field.v1"
_CRYPTPROTECT_UI_FORBIDDEN = 0x1

# Columns holding secrets (profiles + proxies). Names are unique enough to be matched in any table.
SENSITIVE_COLUMNS: frozenset[str] = frozenset(
    {
        "cookies_json",
        "cookies_browser",
        "cookie",
        "cookie_email",
        "password",
        "last_password",
        "old_password",
        "email_backup_password",
        "auth_2fa",
        "totp_secret",
        "refresh_token",
    }
)


def is_protected(value: object) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def protect(value: str | None) -> str | None:
    """Encrypts ``value`` for the current Windows user (no-op for None, "" and already protected values)."""
    if value is None or value == "" or is_protected(value):
        return value
    import win32crypt

    blob = win32crypt.CryptProtectData(
        str(value).encode("utf-8"), None, _ENTROPY, None, None, _CRYPTPROTECT_UI_FORBIDDEN
    )
    return PREFIX + base64.b64encode(blob).decode("ascii")


def reveal(value: Any) -> Any:
    """Decrypts a protected value; anything else (legacy plaintext, None, numbers) is returned unchanged."""
    if not is_protected(value):
        return value
    import win32crypt

    try:
        blob = base64.b64decode(value[len(PREFIX) :])
        _description, data = win32crypt.CryptUnprotectData(blob, _ENTROPY, None, None, _CRYPTPROTECT_UI_FORBIDDEN)
        return data.decode("utf-8")
    except Exception as e:  # other machine/user, corrupted value
        logger.warning("A protected field could not be decrypted (%s); treated as empty", type(e).__name__)
        return ""


def protect_fields(data: Mapping[str, Any]) -> dict[str, Any]:
    """Copy of ``data`` with every sensitive string value protected."""
    return {k: (protect(v) if k in SENSITIVE_COLUMNS and isinstance(v, str) else v) for k, v in data.items()}
