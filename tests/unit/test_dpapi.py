"""Unit tests for Windows DPAPI credential protection.
Validates:
1. dpapi_protect and dpapi_unprotect round-trip on binary data.
2. protect_text and unprotect_text round-trip with envelope prefix.
3. unprotect_text handles legacy plaintext transparently.
4. Purpose separation produces different ciphertexts.
"""

import pytest
from src.infrastructure.credentials.dpapi import (
    TEXT_PREFIX,
    SecretProtectionError,
    dpapi_protect,
    dpapi_unprotect,
    protect_text,
    unprotect_text,
)


def test_dpapi_bytes_roundtrip():
    payload = b"TikTokOAuthSecret_2026_Key_Protected"
    encrypted = dpapi_protect(payload)
    assert encrypted != payload
    decrypted = dpapi_unprotect(encrypted)
    assert decrypted == payload


def test_protect_unprotect_text_roundtrip():
    original = '[{"name": "sessionid", "value": "authentic_session_cookie_123"}]'
    ciphertext = protect_text(original, purpose="database-secrets-v1")
    assert ciphertext.startswith(TEXT_PREFIX)
    assert ciphertext != original

    plaintext = unprotect_text(ciphertext, purpose="database-secrets-v1")
    assert plaintext == original


def test_unprotect_text_legacy_plaintext():
    plain = '{"name": "legacy_cookie", "value": "raw_value"}'
    # Should return plain unchanged
    result = unprotect_text(plain)
    assert result == plain


def test_unprotect_none_or_empty():
    assert unprotect_text(None) is None
    assert unprotect_text("") == ""
    assert protect_text(None) is None
    assert protect_text("") == ""


def test_purpose_separation():
    raw = "SharedSecretData"
    cipher_a = protect_text(raw, purpose="purpose-A")
    cipher_b = protect_text(raw, purpose="purpose-B")
    assert cipher_a != cipher_b

    # Decrypting with wrong purpose should raise SecretProtectionError
    with pytest.raises(SecretProtectionError):
        unprotect_text(cipher_a, purpose="purpose-B")
