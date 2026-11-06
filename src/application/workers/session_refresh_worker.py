"""User-triggered "Làm mới phiên": open the profile on TikTok so the server refreshes the session,
then store the refreshed cookies. Runs off the GUI thread.

Launching goes through OrbitaLaunchWorker, so the same proxy/VPN gate applies (no proxy and no
explicit direct mode => refused). A profile that is already open is only read, never closed.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import pyqtSignal

from src.application.workers.base_worker import BaseWorker, WorkerSignals
from src.application.workers.orbita_launch_worker import OrbitaLaunchWorker
from src.infrastructure.browser.cdp_session import open_url as cdp_open_url

logger = logging.getLogger(__name__)

TIKTOK_HOME = "https://www.tiktok.com/"


class SessionRefreshSignals(WorkerSignals):
    profile_progress = pyqtSignal(int, str, str)  # profile_id, name, message
    done = pyqtSignal(list)  # [{"profile_id", "name", "ok", "logged_in", "expires_at", "message"}]


class SessionRefreshWorker(BaseWorker):
    def __init__(
        self,
        profile_ids: list[int],
        profile_repo: Any,
        proxy_repo: Any,
        launcher: Any,
        session_service: Any,
        proxy_service: Any = None,
        daemon_supervisor: Any = None,
        page_wait_s: float = 20.0,
        open_url: Callable[[str, str], None] = cdp_open_url,
    ) -> None:
        super().__init__()
        self.signals: SessionRefreshSignals = SessionRefreshSignals()
        self.profile_ids = list(profile_ids)
        self.profile_repo = profile_repo
        self.proxy_repo = proxy_repo
        self.launcher = launcher
        self.session_service = session_service
        self.proxy_service = proxy_service
        self.daemon_supervisor = daemon_supervisor
        self.page_wait_s = page_wait_s
        self._open_url = open_url

    def _launch(self, profile_id: int) -> tuple[str | None, str]:
        launch = OrbitaLaunchWorker(
            [profile_id],
            self.profile_repo,
            self.proxy_repo,
            proxy_service=self.proxy_service,
            orbita_launcher=self.launcher,
            daemon_supervisor=self.daemon_supervisor,
        )
        outcome: dict[str, str] = {}
        launch.signals.profile_launched.connect(lambda _i, _n, addr: outcome.update(addr=str(addr)))
        launch.signals.profile_failed.connect(lambda _i, _n, err: outcome.update(err=str(err)))
        launch.run()  # same thread: its gate and launch logic, synchronously
        return outcome.get("addr"), outcome.get("err", "Không mở được trình duyệt")

    def _wait_for_page(self) -> None:
        deadline = time.monotonic() + self.page_wait_s
        while time.monotonic() < deadline and not self.is_cancelled:
            time.sleep(0.25)

    def _refresh_one(self, profile_id: int) -> dict[str, Any]:
        profile = self.profile_repo.get_by_id(profile_id) or {"id": profile_id}
        name = str(profile.get("name") or f"#{profile_id}")
        result: dict[str, Any] = {"profile_id": profile_id, "name": name, "ok": False, "logged_in": False,
                                  "expires_at": None, "message": ""}
        sessions = getattr(self.launcher, "_active_sdk_sessions", {}) or {}
        addr = sessions.get(profile_id)
        launched_here = False
        if not addr:
            self.signals.profile_progress.emit(profile_id, name, "Đang mở trình duyệt…")
            addr, error = self._launch(profile_id)
            if not addr:
                result["message"] = error
                return result
            launched_here = True
            if addr.startswith("PID:"):
                # Binary fallback has no DevTools endpoint: nothing can be read.
                self._close(profile)
                result["message"] = "Trình duyệt không mở qua SDK nên không đọc được phiên"
                return result
        try:
            self.signals.profile_progress.emit(profile_id, name, "Đang tải TikTok để làm mới phiên…")
            try:
                self._open_url(addr, TIKTOK_HOME)
            except Exception as exc:
                logger.info("Could not open TikTok tab for profile %s: %s", profile_id, exc)
            self._wait_for_page()
            capture = self.session_service.capture(profile_id, addr)
            result.update(ok=capture.ok, logged_in=capture.logged_in, expires_at=capture.expires_at,
                          message=capture.message)
        finally:
            if launched_here:
                self._close(profile)
        return result

    def _close(self, profile: dict[str, Any]) -> None:
        try:
            self.launcher.close_profile(profile)
        except Exception as exc:
            logger.warning("Could not close profile %s after session refresh: %s", profile.get("id"), exc)

    def execute(self) -> None:
        results = []
        for profile_id in self.profile_ids:
            if self.is_cancelled:
                break
            try:
                results.append(self._refresh_one(profile_id))
            except Exception as exc:
                logger.error("Session refresh failed for profile %s: %s", profile_id, exc)
                results.append({"profile_id": profile_id, "name": f"#{profile_id}", "ok": False,
                                "logged_in": False, "expires_at": None, "message": str(exc)})
        self.signals.done.emit(results)
