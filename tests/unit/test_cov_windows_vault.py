"""
Additional coverage tests for src/infrastructure/credentials/windows_vault.py.
Target: raise branch from 56% to >= 85%.
All tests are hermetic: keyring API is fully mocked, no real Windows Credential Manager calls.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from src.infrastructure.credentials.windows_vault import WindowsCredentialVault

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeStore:
    """In-memory keyring substitute."""

    def __init__(self):
        self._data: dict[tuple[str, str], str] = {}

    def set_password(self, service, username, password):
        self._data[(service, username)] = password

    def get_password(self, service, username):
        return self._data.get((service, username))

    def delete_password(self, service, username):
        key = (service, username)
        if key not in self._data:
            raise Exception("not found")
        del self._data[key]


def _make_vault(store: _FakeStore) -> tuple[WindowsCredentialVault, _FakeStore]:
    vault = WindowsCredentialVault()
    return vault, store


# ---------------------------------------------------------------------------
# _service_key
# ---------------------------------------------------------------------------

def test_service_key_default_prefix():
    vault = WindowsCredentialVault()
    assert vault._service_key(42) == "TikTokUploadManager.Profile.42"


def test_service_key_custom_prefix():
    vault = WindowsCredentialVault(service_prefix="MyApp.Token")
    assert vault._service_key("abc") == "MyApp.Token.abc"


# ---------------------------------------------------------------------------
# save_oauth_tokens — full payload including expires_at
# ---------------------------------------------------------------------------

def test_save_oauth_tokens_with_expires_at():
    store = _FakeStore()
    vault = WindowsCredentialVault()
    with (
        patch("keyring.set_password", side_effect=store.set_password),
        patch("keyring.get_password", side_effect=store.get_password),
    ):
        result = vault.save_oauth_tokens(
            profile_id=1,
            access_token="fake-access-token-123",
            refresh_token="fake-refresh-token-456",
            client_secret="fake-secret-789",
            expires_at=9999999.0,
        )
        assert result is True

        tokens = vault.get_oauth_tokens(1)
        assert tokens is not None
        assert tokens["access_token"] == "fake-access-token-123"
        assert tokens["expires_at"] == pytest.approx(9999999.0)


def test_save_oauth_tokens_minimal_only_access():
    store = _FakeStore()
    vault = WindowsCredentialVault()
    with (
        patch("keyring.set_password", side_effect=store.set_password),
        patch("keyring.get_password", side_effect=store.get_password),
    ):
        result = vault.save_oauth_tokens(profile_id="p1", access_token="fake-token-only")
        assert result is True
        tokens = vault.get_oauth_tokens("p1")
        assert tokens["access_token"] == "fake-token-only"
        assert tokens["refresh_token"] is None
        assert tokens["client_secret"] is None
        assert tokens["expires_at"] is None


# ---------------------------------------------------------------------------
# save_oauth_tokens — keyring raises
# ---------------------------------------------------------------------------

def test_save_oauth_tokens_keyring_error_returns_false():
    vault = WindowsCredentialVault()
    with patch("keyring.set_password", side_effect=RuntimeError("DPAPI unavailable")):
        result = vault.save_oauth_tokens(profile_id=2, access_token="fake-token")
        assert result is False


# ---------------------------------------------------------------------------
# save_oauth_payload
# ---------------------------------------------------------------------------

def test_save_oauth_payload_full_dict():
    store = _FakeStore()
    vault = WindowsCredentialVault()
    payload = {
        "access_token": "fake-at",
        "refresh_token": "fake-rt",
        "open_id": "user-open-id",
        "scope": "user.info.basic",
        "client_key": "ck123",
        "client_secret": "cs456",
        "expires_at": 1234567890.0,
    }
    with (
        patch("keyring.set_password", side_effect=store.set_password),
        patch("keyring.get_password", side_effect=store.get_password),
    ):
        result = vault.save_oauth_payload(profile_id=5, payload=payload)
        assert result is True
        retrieved = vault.get_oauth_tokens(5)
        assert retrieved is not None
        assert retrieved["open_id"] == "user-open-id"
        assert retrieved["scope"] == "user.info.basic"


def test_save_oauth_payload_keyring_error_returns_false():
    vault = WindowsCredentialVault()
    with patch("keyring.set_password", side_effect=OSError("vault locked")):
        result = vault.save_oauth_payload(profile_id=99, payload={"access_token": "x"})
        assert result is False


# ---------------------------------------------------------------------------
# get_oauth_tokens — error paths
# ---------------------------------------------------------------------------

def test_get_oauth_tokens_returns_none_when_not_set():
    vault = WindowsCredentialVault()
    with patch("keyring.get_password", return_value=None):
        assert vault.get_oauth_tokens(profile_id=404) is None


def test_get_oauth_tokens_returns_none_on_keyring_error():
    vault = WindowsCredentialVault()
    with patch("keyring.get_password", side_effect=Exception("credential manager error")):
        assert vault.get_oauth_tokens(profile_id=500) is None


def test_get_oauth_tokens_returns_none_on_invalid_json():
    vault = WindowsCredentialVault()
    with patch("keyring.get_password", return_value="NOT_VALID_JSON{{{{"):
        # json.loads will raise -> should return None
        result = vault.get_oauth_tokens(profile_id=1)
        assert result is None


# ---------------------------------------------------------------------------
# clear_oauth_tokens — error paths
# ---------------------------------------------------------------------------

def test_clear_oauth_tokens_returns_false_on_delete_error():
    vault = WindowsCredentialVault()
    with patch("keyring.delete_password", side_effect=Exception("not found")):
        assert vault.clear_oauth_tokens(profile_id=0) is False


def test_clear_oauth_tokens_returns_true_on_success():
    store = _FakeStore()
    vault = WindowsCredentialVault()
    with (
        patch("keyring.set_password", side_effect=store.set_password),
        patch("keyring.delete_password", side_effect=store.delete_password),
        patch("keyring.get_password", side_effect=store.get_password),
    ):
        vault.save_oauth_tokens(profile_id=7, access_token="fake-token-7")
        result = vault.clear_oauth_tokens(profile_id=7)
        assert result is True


# ---------------------------------------------------------------------------
# save_proxy_password / get_proxy_password
# ---------------------------------------------------------------------------

def test_save_proxy_password_success():
    store = _FakeStore()
    vault = WindowsCredentialVault()
    with patch("keyring.set_password", side_effect=store.set_password):
        result = vault.save_proxy_password("proxy.example.com", 3128, "proxyuser", "fake-proxy-pass")
        assert result is True


def test_save_proxy_password_error_returns_false():
    vault = WindowsCredentialVault()
    with patch("keyring.set_password", side_effect=PermissionError("vault locked")):
        result = vault.save_proxy_password("host", 1080, "user", "pass")
        assert result is False


def test_get_proxy_password_success():
    store = _FakeStore()
    vault = WindowsCredentialVault()
    with (
        patch("keyring.set_password", side_effect=store.set_password),
        patch("keyring.get_password", side_effect=store.get_password),
    ):
        vault.save_proxy_password("proxy.example.com", 3128, "proxyuser", "fake-proxy-pass")
        result = vault.get_proxy_password("proxy.example.com", 3128, "proxyuser")
        assert result == "fake-proxy-pass"


def test_get_proxy_password_returns_none_when_missing():
    vault = WindowsCredentialVault()
    with patch("keyring.get_password", return_value=None):
        assert vault.get_proxy_password("host", 80, "user") is None


def test_get_proxy_password_returns_none_on_error():
    vault = WindowsCredentialVault()
    with patch("keyring.get_password", side_effect=Exception("vault error")):
        assert vault.get_proxy_password("host", 80, "user") is None


# ---------------------------------------------------------------------------
# Namespace constants
# ---------------------------------------------------------------------------

def test_proxy_namespace_separates_from_profile_namespace():
    """Proxy keys and OAuth keys must not collide."""
    vault = WindowsCredentialVault()
    proxy_key = f"{vault.PROXY_NAMESPACE}.host:3128"
    profile_key = vault._service_key(3128)
    assert proxy_key != profile_key
