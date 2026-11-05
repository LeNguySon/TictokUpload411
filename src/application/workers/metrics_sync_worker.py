"""
Metrics Sync Worker pulling author metrics and creator capabilities without blocking UI.
"""

import logging

from src.application.services.profile_service import ProfileService
from src.application.signals.app_signals import AppSignalBus
from src.application.workers.base_worker import BaseWorker

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
    ) -> None:
        super().__init__()
        self.profile_ids = profile_ids
        self.profile_service = profile_service
        self.signal_bus = signal_bus or AppSignalBus.instance()

    def _safe_emit(self, signal, *args) -> None:
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

            try:
                metrics = self.profile_service.sync_metrics_from_tiktok(profile_id)
                self._safe_emit(self.signal_bus.profile_updated, profile_id, metrics)
            except Exception as e:
                logger.warning("Could not sync metrics for profile %s: %s", profile_id, e)

            pct = ((idx + 1) / total) * 100.0
            self._safe_emit(self.signals.progress, idx + 1, total, pct)
