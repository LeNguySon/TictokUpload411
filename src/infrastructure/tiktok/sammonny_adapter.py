"""
Infrastructure Adapter integrating the SamMonny Tri-Modal TikTok SDK with AgentShield DPAPI Vault.
"""

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
        self.session_factory = session_factory
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
        cover_timestamp_ms: int = 1000,
        progress_callback: Callable[[int, int, float], None] | None = None,
        cancel_token: Callable[[], bool] | None = None,
    ) -> UploadResult:
        """
        Creates an immutable draft and executes the video upload via the appropriate transport mode.
        """
        # Ensure access token is registered if available in Vault
        self._sync_vault_token(profile_id)

        metadata = {
            "title": title,
            "privacy": privacy,
            "tags": tags or [],
            "allow_comment": allow_comment,
            "allow_duet": allow_duet,
            "allow_stitch": allow_stitch,
            "cover_timestamp_ms": cover_timestamp_ms,
        }

        draft = self.publisher.create_draft(video_path=video_path, metadata=metadata)
        logger.info(
            "Draft created: %s for profile_id: %s (size: %d bytes)",
            draft.draft_id,
            profile_id,
            draft.file_size_bytes,
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
