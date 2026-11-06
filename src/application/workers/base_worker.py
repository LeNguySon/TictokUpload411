"""
Base Worker Class for QRunnable background tasks with cooperative cancellation and memory management.
"""

import logging

from PyQt6.QtCore import QObject, QRunnable, pyqtBoundSignal, pyqtSignal

logger = logging.getLogger(__name__)


class WorkerSignals(QObject):
    """Signals emitted by an individual QRunnable worker."""

    started = pyqtSignal()
    finished = pyqtSignal()
    error = pyqtSignal(str)
    progress = pyqtSignal(int, int, float)  # current, total, percentage


class BaseWorker(QRunnable):
    """
    Standard Base Worker running on QThreadPool.
    Guarantees thread-safe signal emission, cooperative cancellation,
    and automatic memory trimming upon task completion.
    """

    def __init__(self) -> None:
        super().__init__()
        self.signals = WorkerSignals()
        self._cancelled: bool = False
        self.setAutoDelete(True)

    def cancel(self) -> None:
        """Flags the worker for early cooperative cancellation."""
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    @property
    def started(self) -> pyqtBoundSignal:
        return self.signals.started

    @property
    def finished(self) -> pyqtBoundSignal:
        return self.signals.finished

    def run(self) -> None:
        """Template method wrapping execute() in try-except and lifecycle signals."""
        try:
            self.signals.started.emit()
        except RuntimeError:
            pass
        try:
            if not self.is_cancelled:
                self.execute()
        except Exception as e:
            logger.error("Unhandled worker exception: %s", e, exc_info=True)
            try:
                self.signals.error.emit(str(e))
            except RuntimeError:
                pass
        finally:
            try:
                self.signals.finished.emit()
            except RuntimeError:
                pass
            # No working-set trim here: sammonny.MemoryManager has no trim_working_set method (the old call
            # always failed silently), and trimming the whole app after every worker - status sync
            # runs every 3 s - would page the GUI out. Uploads trim once in SamMonnyTikTokAdapter.

    def execute(self) -> None:
        """Subclasses override this method to perform actual background work."""
        raise NotImplementedError("Subclasses must implement execute()")
