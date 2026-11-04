"""
Thread Pool Manager managing QThreadPool dispatch, worker concurrency limits, and global cancellation.
"""

import logging
from typing import Any

from PyQt6.QtCore import QObject, QThreadPool

from src.application.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)


class ThreadPoolManager(QObject):
    """
    Singleton manager controlling thread pool execution, preventing GUI starvation,
    and ensuring graceful cancellation of ongoing workers.
    """

    _instance: "ThreadPoolManager | None" = None

    def __init__(self, max_threads: int = 10) -> None:
        super().__init__()
        pool = QThreadPool.globalInstance()
        if pool is None:
            pool = QThreadPool(self)
        self.pool: QThreadPool = pool
        self.pool.setMaxThreadCount(max_threads)
        self._tracked_workers: list[BaseWorker] = []

    @classmethod
    def instance(cls, max_threads: int = 10) -> "ThreadPoolManager":
        if cls._instance is not None:
            try:
                import shiboken6

                if not shiboken6.isValid(cls._instance) or not shiboken6.isValid(cls._instance.pool):
                    cls._instance = None
            except Exception:
                pass

        if cls._instance is not None:
            try:
                _ = cls._instance.pool.maxThreadCount()
            except (RuntimeError, Exception):
                cls._instance = None

        if cls._instance is None:
            cls._instance = cls(max_threads=max_threads)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    @property
    def max_thread_count(self) -> int:
        return self.pool.maxThreadCount()

    def set_max_threads(self, count: int) -> None:
        count = max(1, count)
        self.pool.setMaxThreadCount(count)

    def track_worker(self, worker: BaseWorker) -> None:
        """Adds worker to tracking list for cooperative cancellation."""
        self._tracked_workers.append(worker)

        def _cleanup() -> None:
            if worker in self._tracked_workers:
                self._tracked_workers.remove(worker)

        if hasattr(worker, "signals") and hasattr(worker.signals, "finished"):
            worker.signals.finished.connect(_cleanup)

    def dispatch(self, worker: BaseWorker) -> None:
        """Tracks and launches worker onto the QThreadPool."""
        self.track_worker(worker)
        self.pool.start(worker)

    def submit(self, fn: Any, *args: Any, **kwargs: Any) -> None:
        """Submits an arbitrary callable to the QThreadPool."""
        from PyQt6.QtCore import QRunnable

        class _CallableRunnable(QRunnable):
            def run(self_inner) -> None:
                try:
                    fn(*args, **kwargs)
                except Exception as e:
                    logger.warning("CallableRunnable exception: %s", e)

        self.pool.start(_CallableRunnable())

    @property
    def executor(self) -> "ThreadPoolManager":
        """Provides an executor-compatible submit interface."""
        return self

    def cancel_all(self) -> None:
        """Cooperatively signals all active workers to abort."""
        logger.info("Cancelling %d active background workers", len(self._tracked_workers))
        for worker in list(self._tracked_workers):
            try:
                worker.cancel()
            except Exception as e:
                logger.warning("Error cancelling worker: %s", e)
        self._tracked_workers.clear()

    def active_count(self) -> int:
        return self.pool.activeThreadCount()
