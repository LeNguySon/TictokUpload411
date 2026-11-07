"""
At-rest protection of profile/proxy secrets with Windows DPAPI (CurrentUser scope).
Cookies reach 16 KB, beyond Credential Manager's ~2.5 KB blob limit, so values are encrypted per column.
"""

from __future__ import annotations

import pytest
from src.infrastructure.credentials import field_crypto as fc


def test_protect_reveal_roundtrip_unicode_and_large() -> None:
    value = "sessionid=fake_" + "ạ" * 9000  # > 16 KB of UTF-8
    token = fc.protect(value)
    assert token.startswith(fc.PREFIX)
    assert "sessionid" not in token
    assert fc.reveal(token) == value


def test_protect_is_idempotent_and_keeps_empty_values() -> None:
    once = fc.protect("pw_fake")
    assert fc.protect(once) == once  # never double-encrypted
    assert fc.protect(None) is None
    assert fc.protect("") == ""


def test_reveal_passes_legacy_plaintext_and_non_strings_through() -> None:
    assert fc.reveal("plain legacy cookie") == "plain legacy cookie"
    assert fc.reveal(None) is None
    assert fc.reveal(42) == 42


def test_reveal_of_undecryptable_value_returns_empty_and_does_not_raise() -> None:
    """A DB copied from another machine/user cannot be decrypted: treat as missing, never crash."""
    assert fc.reveal(fc.PREFIX + "bm90LWEtcmVhbC1ibG9i") == ""


def test_is_protected() -> None:
    assert fc.is_protected(fc.protect("x"))
    assert not fc.is_protected("x")
    assert not fc.is_protected(None)


@pytest.mark.parametrize("column", ["cookies_json", "cookies_browser", "password", "totp_secret", "refresh_token"])
def test_sensitive_columns_cover_secrets(column: str) -> None:
    assert column in fc.SENSITIVE_COLUMNS


def test_protect_fields_only_touches_sensitive_keys() -> None:
    data = {"name": "acc", "cookies_json": "sessionid=fake", "password": None, "status": "LIVE"}
    out = fc.protect_fields(data)
    assert out["name"] == "acc" and out["status"] == "LIVE" and out["password"] is None
    assert fc.is_protected(out["cookies_json"]) and fc.reveal(out["cookies_json"]) == "sessionid=fake"
    assert data["cookies_json"] == "sessionid=fake"  # input not mutated


def test_reveal_decrypts_each_value_once_per_process() -> None:
    """Every SELECT * FROM profiles decrypted every cookie again (~1 ms of DPAPI each): 65 profiles = 65 ms per
    list read, several reads per dialog open. A value is now decrypted once and served from memory afterwards."""
    from unittest.mock import patch

    import win32crypt

    token = fc.protect("sessionid=cache_me_fake")
    fc.reveal_cache_clear()
    real = win32crypt.CryptUnprotectData
    with patch.object(win32crypt, "CryptUnprotectData", side_effect=real) as unprotect:
        for _ in range(50):
            assert fc.reveal(token) == "sessionid=cache_me_fake"
    assert unprotect.call_count == 1


def test_undecryptable_values_are_not_cached_as_plaintext() -> None:
    bad = fc.PREFIX + "bm90LWEtcmVhbC1ibG9i"
    fc.reveal_cache_clear()
    assert fc.reveal(bad) == ""
    assert fc.reveal(bad) == ""
