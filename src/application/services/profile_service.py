"""
Profile Application Service coordinating MMO profile lifecycle, metrics sync, and proxy association.
"""

import logging
from typing import Any

from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
from src.infrastructure.tiktok.sammonny_adapter import SamMonnyTikTokAdapter

logger = logging.getLogger(__name__)


class ProfileService:
    """
    Business logic layer for managing TikTok MMO account profiles.
    """

    def __init__(
        self,
        profile_repo: ProfileRepository,
        proxy_repo: ProxyRepository | None = None,
        tiktok_adapter: SamMonnyTikTokAdapter | None = None,
    ) -> None:
        self.profile_repo = profile_repo
        self.proxy_repo = proxy_repo
        self.tiktok_adapter = tiktok_adapter

    def sync_metrics_from_tiktok(self, profile_id: int) -> dict[str, Any]:
        """
        Pulls author metrics and creator capabilities via SamMonny adapter
        and updates the profile record in SQLite.
        """
        if not self.tiktok_adapter:
            raise RuntimeError("TikTok adapter is required to sync live metrics")

        creator_data = self.tiktok_adapter.fetch_creator_metrics(profile_id)

        update_fields: dict[str, Any] = {}
        if "creator_username" in creator_data:
            update_fields["username_on_tiktok"] = creator_data["creator_username"]

        if update_fields:
            self.profile_repo.update(profile_id, **update_fields)

        return creator_data

    def assign_proxy(self, profile_id: int, proxy_id: int) -> bool:
        """
        Binds a proxy to an account profile, ensuring the proxy is not tainted by an IP leak.
        """
        if self.proxy_repo:
            proxy_row = self.proxy_repo.get_by_id(proxy_id)
            if not proxy_row:
                raise ValueError(f"Proxy {proxy_id} does not exist")
            if proxy_row.get("status") == "leak_detected":
                raise ValueError(f"Cannot assign proxy {proxy_id}: Marked as LEAK DETECTED!")

        return self.profile_repo.update(profile_id, proxy_id=proxy_id)

    def move_profiles_to_project(self, profile_ids: list[int], project_id: int) -> int:
        """Transfers multiple profiles to a designated campaign/project."""
        return self.profile_repo.bulk_assign_project(profile_ids=profile_ids, project_id=project_id)

    def trash_profile(self, profile_id: int) -> bool:
        """Moves profile to recycle bin."""
        return self.profile_repo.soft_delete(profile_id)

    def restore_profile(self, profile_id: int) -> bool:
        """Restores profile from recycle bin."""
        return self.profile_repo.restore(profile_id)
