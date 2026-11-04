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


def _default_session_factory(profile_id: str) -> AntidetectSession:
    """Default AntidetectSession factory connecting via SamMonny Engine to Orbita profiles."""
    from sammonny.engine.core import AntidetectEngine

    from src.infrastructure.browser.orbita_launcher import OrbitaLauncher

    engine = AntidetectEngine(profiles_dir=OrbitaLauncher.DAEMON_PROFILES_DIR)
    return engine.session(profile_id=str(profile_id))


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
    ) -> None:
        self.vault = vault or WindowsCredentialVault()
        self.direct_client = direct_client or TikTokDirectPostClient()
        self.session_factory = session_factory or _default_session_factory
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

        return self.publisher.upload(
            draft=draft,
            account_id=str(profile_id),
            progress_callback=progress_callback,
            cancel_token=cancel_token,
        )

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
