"""
Infrastructure Adapter integrating the SamMonny Tri-Modal TikTok SDK with AgentShield DPAPI Vault.
Conforms to TDS-ARCH-001 §6.2 Publisher protocol:
- Direct Post API v2 (Official OAuth with chunked PUT)
- Cookie API Hybrid (ByteDance VOD/TOS 5MB streaming + In-page V8 fetch injection)
- Headless Studio (Zero-leak Chromium CDP DOM + Human Kinematics)
"""

from __future__ import annotations

import contextlib
import logging
import os
import threading
import time
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
from sammonny.engine.core import AntidetectEngine

from src.infrastructure.credentials.windows_vault import WindowsCredentialVault
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
from src.infrastructure.proxy.egress import build_proxy_url, redact_proxy_url, resolve_profile_egress

logger = logging.getLogger(__name__)


def format_proxy_url(proxy_data: dict[str, Any] | None) -> str | None:
    """Proxy URI for HTTP clients (see src.infrastructure.proxy.egress.build_proxy_url)."""
    return build_proxy_url(proxy_data)


class ProxyBoundDirectPostClient(TikTokDirectPostClient):
    """TikTokDirectPostClient whose calls go through the proxy bound to the current upload.

    The SDK publisher calls init_direct_post / upload_video_chunks WITHOUT proxy_url, so official
    uploads left from the machine's own IP. Uploads run concurrently on worker threads: the binding
    is thread-local.
    """

    _PROXIED_METHODS = ("query_creator_info", "init_direct_post", "upload_video_chunks", "get_post_status")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._local = threading.local()

    def current_proxy(self) -> str | None:
        return getattr(self._local, "proxy_url", None)

    @contextlib.contextmanager
    def bound(self, proxy_url: str | None):  # type: ignore[no-untyped-def]
        previous = self.current_proxy()
        self._local.proxy_url = proxy_url
        try:
            yield self
        finally:
            self._local.proxy_url = previous

    def __getattribute__(self, name: str) -> Any:
        attr = super().__getattribute__(name)
        if name in ProxyBoundDirectPostClient._PROXIED_METHODS and callable(attr):
            bound_proxy = super().__getattribute__("current_proxy")()
            if bound_proxy:

                def call(*args: Any, **kwargs: Any) -> Any:
                    if not kwargs.get("proxy_url"):
                        kwargs["proxy_url"] = bound_proxy
                    return attr(*args, **kwargs)

                return call
        return attr


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
                        now = time.time()
                        for it in cookie_items:
                            expires = it.get("expirationDate") or (now + 31536000)
                            if float(expires) <= now:
                                continue  # expired: never hand a dead cookie to the browser
                            cdp_cookies.append(
                                {
                                    "name": it["name"],
                                    "value": it["value"],
                                    "domain": it["domain"],
                                    "path": it.get("path", "/"),
                                    "secure": it.get("secure", True),
                                    "httpOnly": it.get("httpOnly", False),
                                    "expires": float(expires),
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

    from src.domain.policies.cookie_source import pick_session_cookie

    proxy_data = None
    if prof and prof.get("proxy_id"):
        proxy_data = ProxyRepository(db_path=db_path).get_by_id(int(prof["proxy_id"]))
    # Fail closed: no proxy (without the user's direct opt-in) or a leak-flagged proxy never starts
    # an upload browser from the machine's own IP.
    proxy_url = resolve_profile_egress(prof or {"id": profile_id}, proxy_data)
    try:
        OrbitaLauncher().sync_daemon_profile_proxy(target_profile_uuid, proxy_data)
        logger.info("Upload session %s routed via %s", target_profile_uuid, redact_proxy_url(proxy_url))
    except Exception as pe:
        logger.warning("Failed syncing proxy to profile %s: %s", target_profile_uuid, pe)

    cookie_raw = pick_session_cookie(prof)
    if cookie_raw:
        try:
            from src.infrastructure.browser.cookie_injector import BrowserCookieInjector

            # Once per cookie value: re-writing on every upload overwrote the refreshed session.
            BrowserCookieInjector.seed_profile_cookies(OrbitaLauncher.DAEMON_PROFILES_DIR / target_profile_uuid, cookie_raw)
        except Exception as ce:
            logger.debug("Failed pre-seeding cookies: %s", ce)

    engine = AntidetectEngine(profiles_dir=OrbitaLauncher.DAEMON_PROFILES_DIR)
    raw_sess = engine.session(profile_id=target_profile_uuid)
    if lazy:
        return LazyActiveSession(
            raw_sess,
            headless=True,
            cookie_raw=cookie_raw or None,
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
        profile_repo: ProfileRepository | None = None,
        proxy_repo: ProxyRepository | None = None,
    ) -> None:
        self.vault = vault or WindowsCredentialVault()
        self.direct_client = direct_client or ProxyBoundDirectPostClient()
        self.db_path = db_path
        self.profile_repo = profile_repo or ProfileRepository(db_path)
        self.proxy_repo = proxy_repo or ProxyRepository(db_path)
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

    def _profile_egress(self, profile_id: int | str) -> str | None:
        """Proxy URL for this profile's TikTok traffic; raises EgressBlocked when there is none."""
        prof = self.profile_repo.get_by_id(int(profile_id)) if str(profile_id).isdigit() else None
        proxy = self.proxy_repo.get_by_id(prof["proxy_id"]) if prof and prof.get("proxy_id") else None
        return resolve_profile_egress(prof or {"id": profile_id}, proxy)

    def _bind_egress(self, proxy_url: str | None):  # type: ignore[no-untyped-def]
        if isinstance(self.direct_client, ProxyBoundDirectPostClient):
            return self.direct_client.bound(proxy_url)
        return contextlib.nullcontext()

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
        # Resolve the network path first: nothing is sent for a profile without a usable proxy.
        proxy_url = self._profile_egress(profile_id)
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

        # Resolve effective upload mode without mutating self.publisher state (eliminates race condition)
        effective_mode = self.preferred_mode
        if not effective_mode:
            if token:
                effective_mode = UploadMode.OFFICIAL_DIRECT_POST
            elif self.session_factory:
                effective_mode = UploadMode.COOKIE_API_HYBRID
            else:
                effective_mode = UploadMode.HEADLESS_STUDIO

        draft = self.publisher.create_draft(video_path=video_path, metadata=metadata)
        logger.info(
            "Draft created: %s for profile_id: %s (size: %d bytes, mode: %s)",
            draft.draft_id,
            profile_id,
            draft.file_size_bytes,
            effective_mode,
        )

        try:
            with self._bind_egress(proxy_url):  # official Direct Post calls go through the profile proxy
                return self.publisher.upload(
                    draft=draft,
                    account_id=str(profile_id),
                    progress_callback=progress_callback,
                    cancel_token=cancel_token,
                    preferred_mode=effective_mode,
                )
        finally:
            try:
                from sammonny.system.memory import MemoryManager

                # SDK 1.8.1 API (it has no trim_working_set method): trims this app's process tree,
                # including browser children, once per upload.
                MemoryManager.trim_process_tree_memory(os.getpid())
            except Exception as e:
                logger.debug("Post-upload memory trim skipped: %s", e)

    def fetch_creator_metrics(self, profile_id: int | str) -> dict[str, Any]:
        """
        Fetches creator profile metrics (username, nickname, avatar, video duration limits)
        from TikTok Direct Post API using the DPAPI stored token and profile's assigned proxy.
        """
        token = self._sync_vault_token(profile_id)
        if not token:
            raise ValueError(f"No active access token in Windows Vault for profile {profile_id}")

        proxy_url = self._profile_egress(profile_id)  # raises EgressBlocked: never direct

        return self.direct_client.query_creator_info(token, proxy_url=proxy_url)

    def reconcile_status(self, publish_id: str, profile_id: int | str | None = None) -> RemoteStatus:
        """Polls authoritative post status from TikTok for ambiguous or pending uploads."""
        return self.publisher.reconcile(
            publish_id=publish_id,
            account_id=str(profile_id) if profile_id else None,
        )
