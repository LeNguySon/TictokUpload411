"""
Infrastructure Adapter integrating the SamMonny Tri-Modal TikTok SDK with AgentShield DPAPI Vault.
Conforms to TDS-ARCH-001 §6.2 Publisher protocol:
- Direct Post API v2 (Official OAuth with chunked PUT)
- Cookie API Hybrid (ByteDance VOD/TOS 5MB streaming + In-page V8 fetch injection)
- Headless Studio (Zero-leak Chromium CDP DOM + Human Kinematics)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sammonny import (
    AntidetectSession,
    RemoteStatus,
    TikTokDirectPostClient,
    TikTokPublisherAdapter,
    UploadMode,
    UploadResult,
)

from src.infrastructure.credentials.windows_vault import WindowsCredentialVault

logger = logging.getLogger(__name__)


def format_proxy_url(proxy_data: dict[str, Any] | None) -> str | None:
    """Formats proxy dictionary into RFC-compliant proxy URI string."""
    if not proxy_data or not proxy_data.get("host") or not proxy_data.get("port"):
        return None
    proto = str(proxy_data.get("protocol") or "http").lower()
    host = proxy_data["host"]
    port = proxy_data["port"]
    user = proxy_data.get("username")
    pwd = proxy_data.get("password")
    if user and pwd:
        return f"{proto}://{user}:{pwd}@{host}:{port}"
    return f"{proto}://{host}:{port}"


class LazyActiveSession:
    """
    Fluent wrapper around AntidetectSession that lazily starts the browser profile
    and connects the CDP client on first access to cdp, actions, or navigate.
    Ensures safe shutdown and resource cleanup via close().
    """

    def __init__(
        self,
        session: AntidetectSession,
        headless: bool = True,
        cookie_raw: str | None = None,
        proxy_url: str | None = None,
    ) -> None:
        self._session = session
        self._headless = headless
        self._cookie_raw = cookie_raw
        self.proxy_url = proxy_url
        self.proxies: dict[str, str] | None = None
        if proxy_url:
            self.proxies = {"http": proxy_url, "https": proxy_url}

    def _ensure_active(self) -> None:
        if not getattr(self._session, "_cdp", None):
            logger.info(
                "Lazy-starting AntidetectSession for profile %s (headless=%s)...",
                getattr(self._session, "profile_id", "?"),
                self._headless,
            )
            self._session.start(headless=self._headless)
            if self._cookie_raw:
                try:
                    from src.infrastructure.browser.cookie_injector import BrowserCookieInjector

                    cookie_items = BrowserCookieInjector.parse_cookie_string(self._cookie_raw, domain=".tiktok.com")
                    if cookie_items:
                        self._session.cdp.send("Network.enable", {})
                        cdp_cookies = []
                        for it in cookie_items:
                            cdp_cookies.append(
                                {
                                    "name": it["name"],
                                    "value": it["value"],
                                    "domain": it["domain"],
                                    "path": it.get("path", "/"),
                                    "secure": it.get("secure", True),
                                    "httpOnly": it.get("httpOnly", False),
                                    "expires": it.get("expirationDate", 2000000000),
                                }
                            )
                        self._session.cdp.send("Network.setCookies", {"cookies": cdp_cookies})
                        logger.info(
                            "Injected %d cookies via CDP Network.setCookies for profile %s",
                            len(cdp_cookies),
                            getattr(self._session, "profile_id", "?"),
                        )
                except Exception as ce:
                    logger.debug("CDP cookie injection notice: %s", ce)

    @property
    def cdp(self) -> Any:
        self._ensure_active()
        return self._session.cdp

    @property
    def actions(self) -> Any:
        self._ensure_active()
        return self._session.actions

    def navigate(self, url: str) -> Any:
        self._ensure_active()
        return self._session.navigate(url)

    def goto(self, url: str) -> Any:
        self._ensure_active()
        return self._session.goto(url)

    def close(self) -> None:
        try:
            self._session.close()
        except Exception as e:
            logger.warning("Error closing AntidetectSession %s: %s", getattr(self._session, "profile_id", "?"), e)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)

    def __repr__(self) -> str:
        return f"<LazyActiveSession({getattr(self._session, 'profile_id', '?')})>"


def _default_session_factory(
    profile_id: str | int,
    db_path: Path | str | None = None,
    lazy: bool = True,
) -> AntidetectSession:
    """Default AntidetectSession factory connecting via SamMonny Engine to Orbita profiles.
    Resolves integer database profile_id to authentic profile UUID if necessary.
    Returns LazyActiveSession wrapper so that CDP is initiated upon first demand.
    """
    from sammonny.engine.core import AntidetectEngine

    from src.infrastructure.browser.orbita_launcher import OrbitaLauncher
    from src.infrastructure.database.repositories.profile_repository import ProfileRepository
    from src.infrastructure.database.repositories.proxy_repository import ProxyRepository

    target_profile_uuid = str(profile_id)
    prof = None
    if str(profile_id).isdigit():
        try:
            repo = ProfileRepository(db_path=db_path)
            prof = repo.get_by_id(int(profile_id))
            if prof and prof.get("uuid"):
                target_profile_uuid = prof["uuid"]
        except Exception as e:
            logger.warning("Could not resolve profile_id %s to UUID: %s", profile_id, e)

    proxy_data = None
    proxy_url = None
    if prof and prof.get("proxy_id"):
        try:
            px_repo = ProxyRepository(db_path=db_path)
            proxy_data = px_repo.get_by_id(int(prof["proxy_id"]))
            if proxy_data:
                OrbitaLauncher().sync_daemon_profile_proxy(target_profile_uuid, proxy_data)
                proxy_url = format_proxy_url(proxy_data)
                logger.info(
                    "Synchronized proxy %s to profile %s preferences (URL: %s)",
                    proxy_data.get("id"),
                    target_profile_uuid,
                    proxy_url,
                )
        except Exception as pe:
            logger.warning("Failed syncing proxy to profile %s: %s", target_profile_uuid, pe)

    # Pre-inject latest cookies into Chromium SQLite store if available
    if prof and (prof.get("cookies_browser") or prof.get("cookies_json")):
        try:
            from src.infrastructure.browser.cookie_injector import BrowserCookieInjector
            cookie_raw = prof.get("cookies_browser") or prof.get("cookies_json") or ""
            target_profile_dir = OrbitaLauncher.DAEMON_PROFILES_DIR / target_profile_uuid
            BrowserCookieInjector.inject_to_chromium_sqlite(target_profile_dir, cookie_raw)
        except Exception as ce:
            logger.debug("Failed pre-injecting SQLite cookies: %s", ce)

    engine = AntidetectEngine(profiles_dir=OrbitaLauncher.DAEMON_PROFILES_DIR)
    raw_sess = engine.session(profile_id=target_profile_uuid)
    if lazy:
        cookie_str = None
        if prof:
            cookie_str = prof.get("cookies_browser") or prof.get("cookies_json")
        return LazyActiveSession(
            raw_sess,
            headless=True,
            cookie_raw=cookie_str,
            proxy_url=proxy_url,
        )  # type: ignore[return-value]
    return raw_sess


class SamMonnyTikTokAdapter:
    """
    Enterprise-grade adapter wrapping SamMonny's TikTokPublisherAdapter.
    Automatically retrieves DPAPI-encrypted OAuth tokens from Windows Vault,
    supports official Direct Post, Cookie Hybrid TOS 5MB, and Headless Studio modes.
    """

    def __init__(
        self,
        vault: WindowsCredentialVault | None = None,
        direct_client: TikTokDirectPostClient | None = None,
        session_factory: Callable[[str], AntidetectSession] | None = None,
        preferred_mode: UploadMode | None = None,
        db_path: Path | str | None = None,
    ) -> None:
        self.vault = vault or WindowsCredentialVault()
        self.direct_client = direct_client or TikTokDirectPostClient()
        self.db_path = db_path
        if session_factory:
            self.session_factory = session_factory
        else:
            self.session_factory = lambda pid: _default_session_factory(pid, db_path=self.db_path)
        self.preferred_mode = preferred_mode

        self.publisher = TikTokPublisherAdapter(
            direct_client=self.direct_client,
            session_factory=self.session_factory,
            preferred_mode=self.preferred_mode,
        )

    def _sync_vault_token(self, profile_id: int | str) -> str | None:
        """Retrieves OAuth access token from Windows Vault and registers it with the publisher."""
        tokens = self.vault.get_oauth_tokens(profile_id)
        if tokens and "access_token" in tokens:
            token = tokens["access_token"]
            self.publisher.register_access_token(str(profile_id), token)
            return token
        return None

    def upload_video(
        self,
        profile_id: int | str,
        video_path: str | Path,
        title: str,
        privacy: str = "SELF_ONLY",
        tags: list[str] | None = None,
        allow_comment: bool = True,
        allow_duet: bool = True,
        allow_stitch: bool = True,
        allow_hd: bool = True,
        is_ai_generated: bool = False,
        schedule_time: str | None = None,
        cover_timestamp_ms: int = 1000,
        progress_callback: Callable[[int, int, float], None] | None = None,
        cancel_token: Callable[[], bool] | None = None,
    ) -> UploadResult:
        """
        Creates an immutable draft and executes the video upload via the appropriate transport mode:
        1. Official Direct Post if OAuth token available.
        2. Cookie Hybrid TOS 5MB streaming if session factory available.
        3. Headless Studio DOM automation fallback.
        """
        # Ensure access token is registered if available in Vault
        token = self._sync_vault_token(profile_id)

        metadata = {
            "title": title,
            "privacy": privacy,
            "tags": tags or [],
            "allow_comment": allow_comment,
            "allow_duet": allow_duet,
            "allow_stitch": allow_stitch,
            "allow_hd": allow_hd,
            "is_ai_generated": is_ai_generated,
            "schedule_time": schedule_time,
            "cover_timestamp_ms": cover_timestamp_ms,
        }

        # Dynamic mode resolution if not forced
        if not self.preferred_mode:
            if token:
                self.publisher.preferred_mode = UploadMode.OFFICIAL_DIRECT_POST
            elif self.session_factory:
                self.publisher.preferred_mode = UploadMode.COOKIE_API_HYBRID

        draft = self.publisher.create_draft(video_path=video_path, metadata=metadata)
        logger.info(
            "Draft created: %s for profile_id: %s (size: %d bytes, mode: %s)",
            draft.draft_id,
            profile_id,
            draft.file_size_bytes,
            self.publisher.preferred_mode,
        )

        active_session: Any = None

        def tracking_session_factory(pid: str) -> Any:
            nonlocal active_session
            s = self.session_factory(pid)
            active_session = s
            return s

        orig_sf = self.publisher.session_factory
        if orig_sf:
            self.publisher.session_factory = tracking_session_factory

        try:
            return self.publisher.upload(
                draft=draft,
                account_id=str(profile_id),
                progress_callback=progress_callback,
                cancel_token=cancel_token,
            )
        finally:
            self.publisher.session_factory = orig_sf
            if active_session and hasattr(active_session, "close"):
                try:
                    active_session.close()
                except Exception as ce:
                    logger.warning("Error closing session after upload: %s", ce)
            try:
                from sammonny.system.memory import MemoryManager

                MemoryManager.trim_working_set()
            except Exception:
                pass

    def fetch_creator_metrics(self, profile_id: int | str) -> dict[str, Any]:
        """
        Fetches creator profile metrics (username, nickname, avatar, video duration limits)
        from TikTok Direct Post API using the DPAPI stored token.
        """
        token = self._sync_vault_token(profile_id)
        if not token:
            raise ValueError(f"No active access token in Windows Vault for profile {profile_id}")

        return self.direct_client.query_creator_info(token)

    def reconcile_status(self, publish_id: str, profile_id: int | str | None = None) -> RemoteStatus:
        """Polls authoritative post status from TikTok for ambiguous or pending uploads."""
        return self.publisher.reconcile(
            publish_id=publish_id,
            account_id=str(profile_id) if profile_id else None,
        )
