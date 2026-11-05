"""
Base Worker Class for QRunnable background tasks with cooperative cancellation and memory management.
"""

import logging

import sammonny
from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

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
    def started(self):
        return self.signals.started

    @property
    def finished(self):
        return self.signals.finished

    @property
    def completed(self):
        return self.signals.completed

    @property
    def failed(self):
        return self.signals.failed

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
            # Trim working set RAM to ensure desktop responsiveness
            try:
                sammonny.MemoryManager.trim_working_set()
            except Exception:
                pass

    def execute(self) -> None:
        """Subclasses override this method to perform actual background work."""
        raise NotImplementedError("Subclasses must implement execute()")
