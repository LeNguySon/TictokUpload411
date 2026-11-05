"""
Thread Pool Manager managing QThreadPool dispatch, worker concurrency limits, and global cancellation.
"""

import logging
from typing import Any

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QObject, QThreadPool

from src.application.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)


# Strong references to dispatched workers until their `finished` signal is handled, independent of
# the ThreadPoolManager singleton. Workers with autoDelete(False) are owned by Python: if their only
# owner were a manager instance (dropped by reset_instance()), the garbage collector could delete the
# C++ QRunnable and its signals while the pool thread is still running/emitting -> access violation.
_INFLIGHT: dict[int, Any] = {}

DEFAULT_UPLOAD_THREADS = 10
# Short support workers (status sync, metrics, proxy checks, imports) always keep this many slots,
# whatever the user-configured upload concurrency is.
MIN_GENERAL_THREADS = 4

_upload_pool: QThreadPool | None = None


def upload_thread_pool() -> QThreadPool:
    """Dedicated pool for long-running uploads (T8), parented to the application like the UI pool."""
    global _upload_pool
    if _upload_pool is None or sip.isdeleted(_upload_pool):
        app = QCoreApplication.instance()
        _upload_pool = QThreadPool(app) if app is not None else QThreadPool()
        _upload_pool.setMaxThreadCount(DEFAULT_UPLOAD_THREADS)
    return _upload_pool


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
        # Uploads take minutes each; on the general pool they starved every short worker (T8).
        self.upload_pool: QThreadPool = upload_thread_pool()
        # Keyed by id(): membership tests on a list compare sip wrappers with ==, which can touch
        # QRunnables already auto-deleted by the pool (access violation).
        self._tracked_workers: dict[int, BaseWorker] = {}

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
        """User-facing concurrency setting (simultaneous uploads / checks)."""
        return self.upload_pool.maxThreadCount()

    @property
    def max_upload_threads(self) -> int:
        return self.upload_pool.maxThreadCount()

    def set_max_threads(self, count: int) -> None:
        """Sets upload concurrency; the general pool keeps at least MIN_GENERAL_THREADS slots."""
        count = max(1, count)
        self.upload_pool.setMaxThreadCount(count)
        self.pool.setMaxThreadCount(max(count, MIN_GENERAL_THREADS))

    def track_worker(self, worker: BaseWorker) -> None:
        """Adds worker to tracking list for cooperative cancellation."""
        key = id(worker)
        self._tracked_workers[key] = worker
        _INFLIGHT[key] = worker
        tracked = self._tracked_workers

        def _cleanup() -> None:
            # Must not reference the manager itself (see _INFLIGHT).
            tracked.pop(key, None)
            _INFLIGHT.pop(key, None)

        if hasattr(worker, "signals") and hasattr(worker.signals, "finished"):
            worker.signals.finished.connect(_cleanup)

    def dispatch(self, worker: BaseWorker) -> None:
        """Tracks and launches worker onto the QThreadPool."""
        self.track_worker(worker)
        self.pool.start(worker)

    def dispatch_upload(self, worker: BaseWorker) -> None:
        """Tracks and launches a long-running upload worker on the dedicated upload pool."""
        self.track_worker(worker)
        self.upload_pool.start(worker)

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
        for worker in list(self._tracked_workers.values()):
            try:
                worker.cancel()
            except Exception as e:
                logger.warning("Error cancelling worker: %s", e)
        self._tracked_workers.clear()

    def active_count(self) -> int:
        return self.pool.activeThreadCount() + self.upload_pool.activeThreadCount()
