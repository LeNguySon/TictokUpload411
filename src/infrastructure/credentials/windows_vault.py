"""
Windows Credential Vault Adapter (Keyring / DPAPI).
AgentShield Tier-1 Security Compliance.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import keyring

logger = logging.getLogger(__name__)


class WindowsCredentialVault:
    """Manages secure storage of OAuth tokens and proxy credentials in Windows Credential Manager."""

    SERVICE_NAMESPACE = "TikTokUploadManager.Profile"
    PROXY_NAMESPACE = "TikTokUploadManager.Proxy"

    def __init__(self, service_prefix: str | None = None) -> None:
        self.service_prefix = service_prefix or self.SERVICE_NAMESPACE

    def _service_key(self, profile_id: int | str) -> str:
        return f"{self.service_prefix}.{profile_id}"

    def save_oauth_tokens(
        self,
        profile_id: int | str,
        access_token: str,
        refresh_token: str | None = None,
        client_secret: str | None = None,
        expires_at: float | None = None,
    ) -> bool:
        """Stores encrypted OAuth payload in Windows Credential Manager."""
        payload = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "client_secret": client_secret,
            "expires_at": expires_at,
        }
        raw_json = json.dumps(payload)
        key = self._service_key(profile_id)
        try:
            keyring.set_password(key, "oauth_payload", raw_json)
            return True
        except Exception as e:
            logger.error(f"Failed to persist tokens in Windows Vault for profile {profile_id}: {e}")
            return False

    def save_oauth_payload(self, profile_id: int | str, payload: dict[str, Any]) -> bool:
        """Stores the whole (encrypted) OAuth payload: tokens, expiries, open_id, scope, client key/secret."""
        key = self._service_key(profile_id)
        try:
            keyring.set_password(key, "oauth_payload", json.dumps(payload))
            return True
        except Exception as e:
            logger.error(f"Failed to persist OAuth payload in Windows Vault for profile {profile_id}: {e}")
            return False

    def get_oauth_tokens(self, profile_id: int | str) -> dict[str, Any] | None:
        """Retrieves and deserializes OAuth tokens from Windows Credential Manager."""
        key = self._service_key(profile_id)
        try:
            raw_json = keyring.get_password(key, "oauth_payload")
            if not raw_json:
                return None
            tokens: dict[str, Any] = json.loads(raw_json)
            return tokens
        except Exception as e:
            logger.error(f"Failed to read tokens from Windows Vault for profile {profile_id}: {e}")
            return None

    def clear_oauth_tokens(self, profile_id: int | str) -> bool:
        """Deletes stored credentials for the specified profile."""
        key = self._service_key(profile_id)
        try:
            keyring.delete_password(key, "oauth_payload")
            return True
        except Exception:
            return False

    def save_proxy_password(self, host: str, port: int, username: str, password: str) -> bool:
        """Stores proxy password under host:port identifier."""
        key = f"{self.PROXY_NAMESPACE}.{host}:{port}"
        try:
            keyring.set_password(key, username, password)
            return True
        except Exception as e:
            logger.error(f"Failed to store proxy password in Windows Vault: {e}")
            return False

    def get_proxy_password(self, host: str, port: int, username: str) -> str | None:
        key = f"{self.PROXY_NAMESPACE}.{host}:{port}"
        try:
            return keyring.get_password(key, username)
        except Exception:
            return None
