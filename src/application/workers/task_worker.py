"""
Generic background task runner for short UI-support work (DB reads, file scans, HTTP pokes).

Runs on a dedicated small QThreadPool so it never queues behind long upload workers on the
global pool, and delivers result/error back on the GUI thread via queued Qt signals.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QThreadPool, pyqtSignal

from src.application.workers.base_worker import BaseWorker, WorkerSignals

logger = logging.getLogger(__name__)

UI_POOL_MAX_THREADS = 4

_ui_pool: QThreadPool | None = None
# Keeps Python wrappers (and their signal objects) alive until the task has finished.
_running: set[TaskWorker] = set()


def ui_thread_pool() -> QThreadPool:
    """Shared pool for short UI-support tasks, separate from QThreadPool.globalInstance()."""
    global _ui_pool
    if _ui_pool is None or sip.isdeleted(_ui_pool):
        # Parented to the application so Qt destroys it (after waiting for its threads) together
        # with QApplication; an unparented module-level pool is torn down by Python's finalizer
        # after QApplication is gone, which crashes the interpreter on exit.
        app = QCoreApplication.instance()
        _ui_pool = QThreadPool(app) if app is not None else QThreadPool()
        _ui_pool.setMaxThreadCount(UI_POOL_MAX_THREADS)
    return _ui_pool


class TaskSignals(WorkerSignals):
    result = pyqtSignal(object)


class TaskWorker(BaseWorker):
    """Runs ``fn(*args, **kwargs)`` off the GUI thread and emits ``result`` or ``error``."""

    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.signals = TaskSignals()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def execute(self) -> None:
        value = self._fn(*self._args, **self._kwargs)
        if not self.is_cancelled:
            self.signals.result.emit(value)

    def run(self) -> None:
        # Unlike BaseWorker.run, no working-set trim: these tasks are short and frequent, and
        # trimming would page the app's memory out right before the GUI needs it.
        try:
            if not self.is_cancelled:
                self.execute()
        except Exception as e:
            logger.warning("Background task %s failed: %s", getattr(self._fn, "__name__", self._fn), e)
            try:
                self.signals.error.emit(str(e))
            except RuntimeError:
                pass
        finally:
            try:
                self.signals.finished.emit()
            except RuntimeError:
                pass


def run_task(
    fn: Callable[..., Any],
    *args: Any,
    on_result: Callable[[Any], None] | None = None,
    on_error: Callable[[str], None] | None = None,
    pool: QThreadPool | None = None,
    **kwargs: Any,
) -> TaskWorker:
    """Schedules ``fn`` on the UI pool; callbacks are invoked on the GUI thread."""
    worker = TaskWorker(fn, *args, **kwargs)
    worker.setAutoDelete(False)  # lifetime is managed by _running
    if on_result is not None:
        worker.signals.result.connect(on_result)
    if on_error is not None:
        worker.signals.error.connect(on_error)
    _running.add(worker)
    worker.signals.finished.connect(lambda: _running.discard(worker))
    (pool or ui_thread_pool()).start(worker)
    return worker


def drain_ui_tasks(timeout_s: float = 5.0) -> bool:
    """Processes Qt events until every scheduled task (and the callbacks it triggers, which may
    schedule more tasks) has finished. For tests and orderly shutdown; returns False on timeout."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if not _running:
            QCoreApplication.processEvents()  # deliver callbacks queued by the last task
            if not _running:
                return True
        time.sleep(0.005)
    return False


def process_events_until(predicate: Callable[[], bool], timeout_s: float = 5.0) -> bool:
    """Processes Qt events until ``predicate()`` is true (e.g. a debounce timer has fired)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()
