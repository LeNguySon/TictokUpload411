"""
Proxy Check Worker performing non-blocking health checks and IP leak scans across proxy pool.
"""

import logging

from src.application.services.proxy_service import ProxyService
from src.application.signals.app_signals import AppSignalBus
from src.application.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)


class ProxyCheckWorker(BaseWorker):
    """
    Background worker verifying connectivity and guarding against IP leaks for a list of proxies.
    """

    def __init__(
        self,
        proxy_ids: list[int],
        proxy_service: ProxyService,
        signal_bus: AppSignalBus | None = None,
    ) -> None:
        super().__init__()
        self.proxy_ids = proxy_ids
        self.proxy_service = proxy_service
        self.signal_bus = signal_bus or AppSignalBus.instance()

    def execute(self) -> None:
        total = len(self.proxy_ids)
        if total == 0:
            return

        logger.info("Starting proxy health audit worker for %d proxies", total)

        for idx, proxy_id in enumerate(self.proxy_ids):
            if self.is_cancelled:
                logger.info("Proxy audit cancelled cooperatively at index %d", idx)
                break

            try:
                result = self.proxy_service.check_proxy(proxy_id)
                status_str = "alive" if result.is_alive else (result.error or "dead")
                self.signal_bus.proxy_checked.emit(
                    proxy_id,
                    result.is_alive,
                    result.latency_ms if result.is_alive else -1.0,
                    status_str,
                )

                if result.error and "leak" in result.error.lower():
                    self.signal_bus.proxy_leak_detected.emit(proxy_id, result.error)

            except Exception as e:
                logger.error("Failed to check proxy %s: %s", proxy_id, e)
                self.signal_bus.proxy_checked.emit(proxy_id, False, -1.0, str(e))

            pct = ((idx + 1) / total) * 100.0
            self.signals.progress.emit(idx + 1, total, pct)
