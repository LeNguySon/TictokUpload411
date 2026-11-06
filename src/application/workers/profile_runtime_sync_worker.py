"""Profile Runtime Synchronization Worker: Asynchronously checks browser execution states
without blocking the Qt Main Thread, ensuring 60 FPS UI responsiveness.
Conforms to ECC Tier-4 Industrial Concurrency Standards.
"""

from __future__ import annotations

import logging
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal

from src.application.workers.base_worker import BaseWorker, WorkerSignals
from src.infrastructure.browser.orbita_launcher import OrbitaLauncher

logger = logging.getLogger(__name__)


class ProfileRuntimeSyncSignals(WorkerSignals):
    """Signals emitted during background profile execution status synchronization."""

    statuses_updated = pyqtSignal(dict)  # {profile_id: new_status}

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)


class ProfileRuntimeSyncWorker(BaseWorker):
    """
    QRunnable background worker running on QThreadPool that queries OrbitaLauncher batch execution status,
    detects state changes (stopped -> running or running -> stopped/LIVE),
    and dispatches delta updates back to the UI thread via Qt signals.
    """

    def __init__(
        self,
        profiles: list[dict[str, Any]],
        launcher: OrbitaLauncher,
        parent: QObject | None = None,
        profile_repo: Any | None = None,
    ) -> None:
        super().__init__()
        self.profiles = profiles
        self.launcher = launcher
        self.profile_repo = profile_repo
        self.signals: ProfileRuntimeSyncSignals = ProfileRuntimeSyncSignals(parent)
        self.setAutoDelete(False)  # Managed cooperatively by caller / ThreadPoolManager

    def execute(self) -> None:
        """Executes off-thread batch inspection and emits delta dictionary."""
        if not self.profiles or self.is_cancelled:
            return

        running_map = self.launcher.batch_check_profiles_running(self.profiles)
        if self.is_cancelled:
            return

        deltas: dict[int, str] = {}
        for p in self.profiles:
            if self.is_cancelled:
                return

            p_id = p.get("id")
            if p_id is None:
                continue

            current_status = p.get("status", "stopped")
            is_running = running_map.get(p_id, False)

            if is_running and current_status != "running":
                deltas[p_id] = "running"
            elif not is_running and current_status == "running":
                has_session = p.get("cookies_browser") or p.get("cookies_json") or p.get("cookie")
                new_status = "LIVE" if (has_session or p.get("username_on_tiktok")) else "stopped"
                deltas[p_id] = new_status

        if deltas and not self.is_cancelled:
            self._persist_deltas(deltas)
            try:
                self.signals.statuses_updated.emit(deltas)
            except RuntimeError as re:
                logger.debug("Signal target deleted before status emit: %s", re)

    def _persist_deltas(self, deltas: dict[int, str]) -> None:
        """Writes status changes on this worker thread (grouped: one UPDATE per status value),
        so the GUI slot never blocks on SQLite's writer lock."""
        if self.profile_repo is None:
            return
        by_status: dict[str, list[int]] = {}
        for p_id, status in deltas.items():
            by_status.setdefault(status, []).append(p_id)
        for status, ids in by_status.items():
            try:
                self.profile_repo.bulk_update_fields(ids, {"status": status})
            except Exception as e:
                logger.warning("Failed persisting runtime status %s for %d profiles: %s", status, len(ids), e)
