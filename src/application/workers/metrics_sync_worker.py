"""
Metrics Sync Worker pulling author metrics and creator capabilities without blocking UI.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import pyqtBoundSignal

from src.application.services.profile_service import ProfileService
from src.application.signals.app_signals import AppSignalBus
from src.application.workers.base_worker import BaseWorker

if TYPE_CHECKING:
    from src.infrastructure.database.repositories.profile_repository import ProfileRepository
    from src.infrastructure.database.repositories.proxy_repository import ProxyRepository

logger = logging.getLogger(__name__)


class MetricsSyncWorker(BaseWorker):
    """
    Background worker updating live statistics (followers, video counts, earnings)
    for managed TikTok profiles.
    """

    def __init__(
        self,
        profile_ids: list[int],
        profile_service: ProfileService,
        signal_bus: AppSignalBus | None = None,
        proxy_repo: ProxyRepository | None = None,
        profile_repo: ProfileRepository | None = None,
    ) -> None:
        super().__init__()
        self.profile_ids = profile_ids
        self.profile_service = profile_service
        self.signal_bus = signal_bus or AppSignalBus.instance()
        self.proxy_repo = proxy_repo or getattr(profile_service, "proxy_repo", None)
        self.profile_repo = profile_repo or getattr(profile_service, "profile_repo", None)

    def _safe_emit(self, signal: pyqtBoundSignal, *args: Any) -> None:
        try:
            signal.emit(*args)
        except RuntimeError:
            pass

    def execute(self) -> None:
        total = len(self.profile_ids)
        if total == 0:
            return

        logger.info("Starting live metrics synchronization for %d profiles", total)

        for idx, profile_id in enumerate(self.profile_ids):
            if self.is_cancelled:
                break

            # AgentShield Strict Proxy Gate: skip unproxied or leak_detected profile
            prof = self.profile_repo.get_by_id(profile_id) if self.profile_repo else None
            if prof:
                proxy_id = prof.get("proxy_id")
                if not proxy_id:
                    logger.warning(
                        "AgentShield Strict Proxy Gate: Skipping metrics sync for Profile #%s (no proxy assigned)",
                        profile_id,
                    )
                    pct = ((idx + 1) / total) * 100.0
                    self._safe_emit(self.signals.progress, idx + 1, total, pct)
                    continue

                if self.proxy_repo:
                    px = self.proxy_repo.get_by_id(proxy_id)
                    if px and px.get("status") == "leak_detected":
                        logger.warning(
                            "AgentShield Strict Proxy Gate: Skipping metrics sync for Profile #%s (proxy %s leak detected)",
                            profile_id,
                            proxy_id,
                        )
                        pct = ((idx + 1) / total) * 100.0
                        self._safe_emit(self.signals.progress, idx + 1, total, pct)
                        continue

            try:
                metrics = self.profile_service.sync_metrics_from_tiktok(profile_id)
                self._safe_emit(self.signal_bus.profile_updated, profile_id, metrics)
            except Exception as e:
                logger.warning("Could not sync metrics for profile %s: %s", profile_id, e)

            pct = ((idx + 1) / total) * 100.0
            self._safe_emit(self.signals.progress, idx + 1, total, pct)
