"""
Infrastructure Adapter integrating the SamMonny Tri-Modal TikTok SDK with AgentShield DPAPI Vault.
Conforms to TDS-ARCH-001 §6.2 Publisher protocol:
- Direct Post API v2 (Official OAuth with chunked PUT)
- Cookie API Hybrid (ByteDance VOD/TOS 5MB streaming + In-page V8 fetch injection)
- Headless Studio (Zero-leak Chromium CDP DOM + Human Kinematics)
"""

from __future__ import annotations

import contextlib
import dataclasses
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

from src.infrastructure.browser.daemon_proxy_sync import sync_daemon_proxy
from src.infrastructure.credentials.windows_vault import WindowsCredentialVault
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
from src.infrastructure.proxy.egress import build_proxy_url, redact_proxy_url, resolve_profile_egress

logger = logging.getLogger(__name__)


def _install_sdk_compat_shims() -> None:
    """Works around SamMonny SDK defects that would otherwise fail silently inside the SDK.

    Unreleased SDK main after 1.8.3 called ``random.uniform`` in TikTokHeadlessStudioUploader's Post click
    without importing ``random`` (fixed in 1.8.4): the NameError was swallowed, the Post button never clicked
    and Studio uploads ended ambiguous. Binding the module is harmless on builds that already import it.
    """
    import random

    import sammonny.platforms.tiktok as sdk_tiktok

    if getattr(sdk_tiktok, "random", None) is not random:
        sdk_tiktok.random = random  # type: ignore[attr-defined]


_install_sdk_compat_shims()

PUBLIC_PRIVACY = "PUBLIC_TO_EVERYONE"
# SamMonny SDK 1.8.4: Hybrid 3-phase ByteDance TOS streaming + in-page V8 fetch verified live
# on 2026-11-07 (VID: v24025gl0000dbndcqnog65pmnbj4j7g, Item ID: 7705331779309227286).
COOKIE_HYBRID_AVAILABLE = True


class UploadMethodError(RuntimeError):
    """The chosen upload method cannot (or must not) upload this video; nothing was sent."""


class DomUploadBlocked(PermissionError):
    """A DOM (TikTok Studio page) upload was attempted where it is not allowed for this upload."""


class _GuardedCdp:
    """CDP client proxy that refuses to attach a file to the Studio page (the DOM upload step).

    The SDK's hybrid uploader falls back to a DOM upload by itself; the DOM path ignores privacy and
    schedule and may repost after an ambiguous hybrid publish. Blocking DOM.setFileInputFiles stops it
    before anything is posted while the hybrid path (signing / fetch) keeps working.
    """

    def __init__(self, cdp: Any, reason: str) -> None:
        self._cdp = cdp
        self._reason = reason

    def send(self, method: str, params: Any = None, *args: Any, **kwargs: Any) -> Any:
        if method == "DOM.setFileInputFiles":
            raise DomUploadBlocked(f"Upload qua trình duyệt Studio (DOM) bị chặn: {self._reason}")
        return self._cdp.send(method, params, *args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cdp, name)


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
        dom_upload_allowed: bool = True,
        dom_block_reason: str = "",
    ) -> None:
        self._session = session
        self._headless = headless
        self._dom_upload_allowed = dom_upload_allowed
        self._dom_block_reason = dom_block_reason
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

            # Establish authentic tiktok.com origin context so in-browser V8 fetch works seamlessly
            try:
                curr = str(self._session.cdp.evaluate("window.location.href") or "")
                if "tiktok.com" not in curr:
                    self._session.navigate("https://www.tiktok.com/tiktokstudio/upload")
                    time.sleep(2.0)
            except Exception as ne:
                logger.debug("Initial origin navigation notice: %s", ne)

    @property
    def cdp(self) -> Any:
        self._ensure_active()
        if not self._dom_upload_allowed:
            return _GuardedCdp(self._session.cdp, self._dom_block_reason)
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
    headless: bool = True,
    dom_upload_allowed: bool = True,
    dom_block_reason: str = "",
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
    # The daemon starts this browser from ITS OWN profile record: set and verify it (raises on
    # mismatch, so the upload browser never runs on a stale / missing proxy).
    sync_daemon_proxy(target_profile_uuid, proxy_data if proxy_url else None)
    try:
        OrbitaLauncher().sync_daemon_profile_proxy(target_profile_uuid, proxy_data)
    except Exception as pe:
        logger.warning("Failed syncing proxy to profile %s preferences: %s", target_profile_uuid, pe)
    logger.info("Upload session %s routed via %s", target_profile_uuid, redact_proxy_url(proxy_url))

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
            headless=headless,
            cookie_raw=cookie_raw or None,
            proxy_url=proxy_url,
            dom_upload_allowed=dom_upload_allowed,
            dom_block_reason=dom_block_reason,
        )  # type: ignore[return-value]
    return raw_sess


class SamMonnyTikTokAdapter:
    # Official uploads: poll TikTok's post status every 5 s, ~5 minutes at most.
    reconcile_poll_s: float = 5.0
    reconcile_attempts: int = 60

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
        token_manager: Any = None,
    ) -> None:
        self.vault = vault or WindowsCredentialVault()
        self.direct_client = direct_client or ProxyBoundDirectPostClient()
        self.db_path = db_path
        self.profile_repo = profile_repo or ProfileRepository(db_path)
        self.proxy_repo = proxy_repo or ProxyRepository(db_path)
        from src.application.settings.upload_settings import UploadMethod, UploadSettings

        self._ctx = threading.local()
        if session_factory:
            self.session_factory = session_factory
        else:
            self.session_factory = lambda pid: _default_session_factory(
                pid, db_path=self.db_path, **self._session_options()
            )
        self.preferred_mode = preferred_mode
        legacy = {
            UploadMode.OFFICIAL_DIRECT_POST: UploadMethod.OFFICIAL,
            UploadMode.COOKIE_API_HYBRID: UploadMethod.HYBRID,
            UploadMode.HEADLESS_STUDIO: UploadMethod.STUDIO,
        }
        self.settings = UploadSettings(method=legacy.get(preferred_mode, UploadMethod.AUTO))  # type: ignore[arg-type]
        if token_manager is None:
            from src.application.services.token_manager import TokenManager

            # Refreshes OAuth tokens before they expire (rotated refresh token stored in the Vault first).
            token_manager = TokenManager(
                vault=self.vault,
                profile_repo=self.profile_repo,
                client=self.direct_client,
                egress=lambda pid: self._profile_egress(pid),
            )
        self.token_manager = token_manager

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

    def apply_settings(self, settings: Any) -> None:
        """Upload method chosen by the user (Cài Đặt Upload)."""
        self.settings = settings

    def _upload_context(self) -> dict[str, Any]:
        return dict(getattr(self._ctx, "values", None) or {"dom_allowed": True, "dom_block_reason": "",
                                                            "show_browser": False})

    def _session_options(self) -> dict[str, Any]:
        ctx = self._upload_context()
        return {
            "headless": not ctx.get("show_browser", False),
            "dom_upload_allowed": bool(ctx.get("dom_allowed", True)),
            "dom_block_reason": str(ctx.get("dom_block_reason", "")),
        }

    @contextlib.contextmanager
    def _upload_scope(self, **values: Any):  # type: ignore[no-untyped-def]
        previous = getattr(self._ctx, "values", None)
        self._ctx.values = values
        try:
            yield
        finally:
            self._ctx.values = previous

    def _vault_token(self, profile_id: int | str) -> str | None:
        tokens = self.vault.get_oauth_tokens(profile_id)
        return tokens["access_token"] if tokens and "access_token" in tokens else None

    def _resolve_mode(self, profile_id: int | str, token: str | None) -> UploadMode:
        from src.application.settings.upload_settings import UploadMethod

        method = getattr(self.settings, "method", UploadMethod.AUTO)
        if method is UploadMethod.OFFICIAL:
            if not token:
                raise UploadMethodError(
                    f"Hồ sơ #{profile_id} chưa có OAuth token cho API chính thức. Kết nối TikTok API cho hồ sơ "
                    "hoặc chọn phương pháp khác trong Cài Đặt Upload."
                )
            return UploadMode.OFFICIAL_DIRECT_POST
        if method is UploadMethod.HYBRID:
            if not COOKIE_HYBRID_AVAILABLE:
                raise UploadMethodError(
                    "Cookie API (Hybrid) hiện chưa hoạt động: SDK chưa truyền dữ liệu video thật. "
                    "Chọn 'Tự động', 'API chính thức' hoặc 'Trình duyệt TikTok Studio' trong Cài Đặt Upload."
                )
            return UploadMode.COOKIE_API_HYBRID
        if method is UploadMethod.STUDIO:
            return UploadMode.HEADLESS_STUDIO
        # Auto: the official API when the profile is connected, otherwise the Studio page.
        return UploadMode.OFFICIAL_DIRECT_POST if token else UploadMode.HEADLESS_STUDIO

    def supports_native_schedule(self, profile_id: int | str) -> bool:
        """True only if the method used for this profile can let TikTok hold a scheduled post.

        Official Direct Post and the Studio DOM ignore schedule_time (they post immediately), so the
        app must keep those videos and publish them itself at the scheduled time.
        """
        try:
            mode = self._resolve_mode(profile_id, self._vault_token(profile_id))
        except UploadMethodError:
            return False
        return COOKIE_HYBRID_AVAILABLE and mode is UploadMode.COOKIE_API_HYBRID

    def _reconcile_official(self, result: UploadResult, profile_id: int | str) -> UploadResult:
        """Polls TikTok until an official upload is really published (or failed)."""
        publish_id = str(result.publish_id or "")
        status = result.status
        for _ in range(max(1, int(self.reconcile_attempts))):
            status = self.publisher.reconcile(publish_id, account_id=str(profile_id))
            if status in (RemoteStatus.PUBLISH_COMPLETE, RemoteStatus.FAILED):
                break
            time.sleep(self.reconcile_poll_s)
        if status == RemoteStatus.FAILED:
            return UploadResult(
                success=False,
                draft_id=result.draft_id,
                publish_id=publish_id,
                status=RemoteStatus.FAILED,
                error=f"TikTok báo xử lý video thất bại (publish_id {publish_id}).",
            )
        return dataclasses.replace(result, status=status)

    def _sync_vault_token(self, profile_id: int | str, force_refresh: bool = False) -> str | None:
        """Valid OAuth access token (refreshed when needed) registered with the publisher."""
        token: str | None = self.token_manager.get_valid_access_token(profile_id, force=force_refresh)
        if token:
            self.publisher.register_access_token(str(profile_id), token)
        return token

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

        # The method chosen in Cài Đặt Upload is honoured: no silent switch (the SDK would always force
        # the official API when a token exists and fall back to a browser upload when it fails).
        from src.application.settings.upload_settings import UploadMethod

        allow_fallback = bool(getattr(self.settings, "allow_fallback", False))
        privacy = str(privacy or "SELF_ONLY")
        # The Studio page cannot set privacy or a schedule: such videos need the official API.
        dom_reasons = []
        if privacy != PUBLIC_PRIVACY:
            dom_reasons.append(f"video đặt quyền riêng tư {privacy} (DOM luôn đăng công khai)")
        if schedule_time:
            dom_reasons.append("video có giờ hẹn (DOM đăng ngay)")

        effective_mode = self._resolve_mode(profile_id, token)
        if (
            effective_mode is UploadMode.HEADLESS_STUDIO
            and dom_reasons
            and getattr(self.settings, "method", UploadMethod.AUTO) is UploadMethod.AUTO
        ):
            raise UploadMethodError(
                f"Hồ sơ #{profile_id} chưa kết nối TikTok API: " + "; ".join(dom_reasons)
                + " — chỉ đăng được qua API chính thức. Kết nối TikTok API cho hồ sơ này."
            )
        if effective_mode is UploadMode.OFFICIAL_DIRECT_POST:
            try:
                with self._bind_egress(proxy_url):
                    try:
                        info = self.direct_client.query_creator_info(token) or {}
                    except Exception as first:
                        if "401" not in str(first):
                            raise
                        token = self._sync_vault_token(profile_id, force_refresh=True)  # expired: refresh once
                        info = self.direct_client.query_creator_info(token) or {}
            except Exception as exc:
                if not allow_fallback or dom_reasons:
                    # No fallback: not allowed, or the only other working method (Studio) cannot do it.
                    raise UploadMethodError(f"API chính thức không dùng được cho hồ sơ #{profile_id}: {exc}") from exc
                logger.warning("Official API unavailable for profile %s (%s): falling back to TikTok Studio",
                               profile_id, exc)
                effective_mode = UploadMode.HEADLESS_STUDIO
            else:
                allowed = list(info.get("privacy_level_options") or [])
                if allowed and privacy not in allowed:
                    raise UploadMethodError(
                        f"Tài khoản không được đăng với quyền riêng tư {privacy} qua API chính thức "
                        f"(được phép: {', '.join(allowed)})."
                    )
        if effective_mode is not UploadMode.OFFICIAL_DIRECT_POST:
            self.publisher._tokens.pop(str(profile_id), None)  # otherwise the SDK forces the API again

        if effective_mode is UploadMode.HEADLESS_STUDIO and dom_reasons:
            raise UploadMethodError(
                "Trình duyệt Studio (DOM) không đặt được quyền riêng tư và giờ hẹn: " + "; ".join(dom_reasons)
                + ". Chọn phương pháp khác trong Cài Đặt Upload."
            )
        # A DOM upload may only happen when the Studio method was chosen / routed here (never a silent
        # SDK switch); the session guard blocks DOM.setFileInputFiles otherwise.
        dom_allowed = effective_mode is UploadMode.HEADLESS_STUDIO
        if not dom_allowed:
            dom_reasons.append("phương pháp upload không phải Trình duyệt Studio")

        draft = self.publisher.create_draft(video_path=video_path, metadata=metadata)
        logger.info(
            "Draft created: %s for profile_id: %s (size: %d bytes, mode: %s)",
            draft.draft_id,
            profile_id,
            draft.file_size_bytes,
            effective_mode,
        )

        try:
            with (
                self._bind_egress(proxy_url),  # official Direct Post calls go through the profile proxy
                self._upload_scope(
                    dom_allowed=dom_allowed,
                    dom_block_reason="; ".join(dom_reasons),
                    show_browser=bool(getattr(self.settings, "studio_show_browser", False)),
                ),
            ):
                result = self.publisher.upload(
                    draft=draft,
                    account_id=str(profile_id),
                    progress_callback=progress_callback,
                    cancel_token=cancel_token,
                    preferred_mode=effective_mode,
                )
                if result.success and str(result.publish_id or "").startswith("studio_post_"):
                    # The SDK's DOM path returns this synthetic id when nothing confirmed the post.
                    return UploadResult(
                        success=False,
                        draft_id=result.draft_id,
                        status=RemoteStatus.UNKNOWN,
                        error="Không xác nhận được bài đăng: hãy kiểm tra trên TikTok Studio trước khi đăng lại.",
                        is_ambiguous=True,
                    )
                if (
                    effective_mode is UploadMode.OFFICIAL_DIRECT_POST
                    and result.success
                    and result.publish_id
                    and getattr(self.settings, "reconcile_official", True)
                ):
                    result = self._reconcile_official(result, profile_id)
                return result
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

        info: dict[str, Any] = self.direct_client.query_creator_info(token, proxy_url=proxy_url)
        return info

    def reconcile_status(self, publish_id: str, profile_id: int | str | None = None) -> RemoteStatus:
        """Polls authoritative post status from TikTok for ambiguous or pending uploads."""
        return self.publisher.reconcile(
            publish_id=publish_id,
            account_id=str(profile_id) if profile_id else None,
        )
