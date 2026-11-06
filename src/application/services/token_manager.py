"""OAuth access tokens for the official TikTok Content Posting API, refreshed automatically.

Rules (developers.tiktok.com, User Access Token Management):
- Refresh with POST /v2/oauth/token/ (grant_type=refresh_token) before the access token expires.
- The refresh token rotates: the new one must be stored, the old one stops working.
- Lifetimes come from the response (expires_in / refresh_expires_in), never hard-coded.

Safety:
- One refresh at a time per profile (a concurrent second refresh would send an already-rotated token).
- The new tokens are written to the Windows Vault BEFORE the access token is used.
- Refresh traffic goes through the profile's egress (proxy rule), like every account request.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

GLOBAL_API_KEY = "GLOBAL_API_CONFIG"
REFRESH_MARGIN_S = 5 * 60


class ReconnectRequired(PermissionError):
    """The profile's TikTok API authorization is gone: the user must connect it again."""


class ApiConfigError(RuntimeError):
    """Client key / secret needed for the refresh are missing or inconsistent."""


class TokenManager:
    def __init__(
        self,
        vault: Any,
        profile_repo: Any,
        client: Any,
        egress: Callable[[int | str], str | None],
        clock: Callable[[], float] = time.time,
        margin_s: float = REFRESH_MARGIN_S,
    ) -> None:
        self.vault = vault
        self.profile_repo = profile_repo
        self.client = client
        self.egress = egress
        self.clock = clock
        self.margin_s = margin_s
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    # ----------------------------------------------------------------- helpers
    def _lock(self, profile_id: int | str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(str(profile_id), threading.Lock())

    def _profile(self, profile_id: int | str) -> dict[str, Any]:
        if not str(profile_id).isdigit():
            return {}
        try:
            return self.profile_repo.get_by_id(int(profile_id)) or {}
        except Exception as exc:  # the profile record only adds optional data (imported refresh token)
            logger.debug("Profile %s not readable for token data: %s", profile_id, exc)
            return {}

    def _payload(self, profile_id: int | str) -> dict[str, Any]:
        payload = dict(self.vault.get_oauth_tokens(profile_id) or {})
        profile = self._profile(profile_id)
        db_refresh = profile.get("refresh_token")
        if db_refresh and not payload.get("refresh_token"):
            # Bulk import stored it in a plaintext DB column: move it into the Vault.
            payload["refresh_token"] = db_refresh
            if not self.vault.save_oauth_payload(profile_id, payload):
                raise RuntimeError("Không lưu được refresh token vào Windows Vault")
            self.profile_repo.update(int(profile_id), refresh_token=None)
            logger.info("Moved profile %s refresh token from the database into the Vault", profile_id)
        elif db_refresh:
            self.profile_repo.update(int(profile_id), refresh_token=None)
        return payload

    def _client_credentials(self, profile_id: int | str, payload: dict[str, Any]) -> tuple[str, str]:
        glob = dict(self.vault.get_oauth_tokens(GLOBAL_API_KEY) or {})
        # Legacy format stored the client key in "access_token".
        global_key = glob.get("client_key") or glob.get("access_token")
        global_secret = glob.get("client_secret")
        own_key = payload.get("client_key") or self._profile(profile_id).get("client_id")
        if own_key and own_key != global_key:
            own_secret = payload.get("client_secret")
            if not own_secret:
                raise ApiConfigError(
                    f"Hồ sơ #{profile_id} dùng client_id riêng ({own_key}) nhưng chưa có client secret tương ứng."
                )
            return str(own_key), str(own_secret)
        if not global_key or not global_secret:
            raise ApiConfigError("Chưa nhập Client Key / Client Secret trong 'Cấu Hình API & Cookie'.")
        return str(global_key), str(global_secret)

    def _needs_refresh(self, payload: dict[str, Any]) -> bool:
        expires_at = payload.get("expires_at")
        if expires_at is None:
            return bool(payload.get("refresh_token"))
        return float(expires_at) - self.clock() < self.margin_s

    def _flag_reconnect(self, profile_id: int | str, value: int) -> None:
        if str(profile_id).isdigit():
            try:
                self.profile_repo.update(int(profile_id), api_reconnect_required=value)
            except Exception as exc:
                logger.debug("Could not flag profile %s: %s", profile_id, exc)

    # ----------------------------------------------------------------- public
    def get_valid_access_token(self, profile_id: int | str, force: bool = False) -> str | None:
        """Access token usable now (refreshed if needed); None if the profile has no API token."""
        payload = self._payload(profile_id)
        if not payload.get("access_token") and not payload.get("refresh_token"):
            return None
        if not force and not self._needs_refresh(payload):
            return payload.get("access_token")
        if not payload.get("refresh_token"):
            expires_at = payload.get("expires_at")
            if expires_at is not None and float(expires_at) <= self.clock():
                self._flag_reconnect(profile_id, 1)
                raise ReconnectRequired(
                    f"Token API của hồ sơ #{profile_id} đã hết hạn và không có refresh token: kết nối lại TikTok API."
                )
            return payload.get("access_token")

        with self._lock(profile_id):
            payload = self._payload(profile_id)  # another thread may have refreshed meanwhile
            if not force and not self._needs_refresh(payload):
                return payload.get("access_token")
            try:
                client_key, client_secret = self._client_credentials(profile_id, payload)
            except ApiConfigError:
                expires_at = payload.get("expires_at")
                if payload.get("access_token") and (expires_at is None or float(expires_at) > self.clock()):
                    # Cannot refresh (no client key/secret) but the token may still be valid: use it.
                    logger.warning("Profile %s: token not refreshed (missing API client config)", profile_id)
                    return payload.get("access_token")
                raise
            proxy_url = self.egress(profile_id)
            from sammonny.platforms.tiktok import TokenRefreshError

            try:
                tokens = self.client.refresh_access_token(
                    client_key, client_secret, payload["refresh_token"], proxy_url=proxy_url
                )
            except TokenRefreshError as exc:
                if exc.reconnect_required:
                    self._flag_reconnect(profile_id, 1)
                    raise ReconnectRequired(
                        f"TikTok từ chối làm mới token của hồ sơ #{profile_id} ({exc}): kết nối lại TikTok API."
                    ) from exc
                raise

            now = self.clock()
            new_payload = {
                **payload,
                "access_token": tokens.access_token,
                "refresh_token": tokens.refresh_token,
                "expires_at": now + int(tokens.expires_in or 0),
                "refresh_expires_at": now + int(tokens.refresh_expires_in) if tokens.refresh_expires_in else None,
                "open_id": tokens.open_id or payload.get("open_id"),
                "scope": tokens.scope or payload.get("scope"),
            }
            # Store first: the old refresh token no longer works after a refresh.
            if not self.vault.save_oauth_payload(profile_id, new_payload):
                raise RuntimeError(
                    f"Không lưu được token mới của hồ sơ #{profile_id} vào Windows Vault: dừng để không mất phiên."
                )
            self._flag_reconnect(profile_id, 0)
            logger.info("Refreshed TikTok API token for profile %s", profile_id)
            return str(tokens.access_token)
