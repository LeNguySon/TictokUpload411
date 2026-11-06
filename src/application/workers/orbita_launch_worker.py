"""
Orbita Launch Worker: Handles proxy rotation, TCP reachability checks, daemon verification,
and Orbita Antidetect browser launching asynchronously on background QThreadPool.
Conforms to ECC Development Standards and guarantees zero GUI freeze.
"""

from __future__ import annotations

import logging
import socket
from typing import Any

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository

logger = logging.getLogger(__name__)


class OrbitaLaunchSignals(QObject):
    """Signals emitted during asynchronous browser launch sequence."""

    started = pyqtSignal()
    profile_started = pyqtSignal(int, str)  # profile_id, profile_name
    profile_launched = pyqtSignal(int, str, str)  # profile_id, profile_name, cdp_or_pid
    profile_failed = pyqtSignal(int, str, str)  # profile_id, profile_name, error_message
    batch_completed = pyqtSignal(int, int)  # success_count, total_count
    finished = pyqtSignal()


class OrbitaLaunchWorker(QRunnable):
    """
    QRunnable worker executing browser preparation, proxy rotation, and launching
    in a dedicated worker thread, completely decoupling I/O from the Qt Main Thread.
    """

    def __init__(
        self,
        profile_ids: list[int],
        profile_repo: ProfileRepository,
        proxy_repo: ProxyRepository,
        proxy_service: Any = None,
        orbita_launcher: Any = None,
        daemon_supervisor: Any = None,
    ) -> None:
        super().__init__()
        self.profile_ids = profile_ids
        self.profile_repo = profile_repo
        self.proxy_repo = proxy_repo
        self.proxy_service = proxy_service
        self.orbita_launcher = orbita_launcher
        self.daemon_supervisor = daemon_supervisor

        self.signals: OrbitaLaunchSignals = OrbitaLaunchSignals()
        self._cancelled: bool = False
        self.setAutoDelete(True)

    def cancel(self) -> None:
        """Flags the launch worker for early cancellation."""
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def _check_proxy_alive(self, proxy_data: dict[str, Any], timeout: float = 1.5) -> bool:
        """Non-blocking TCP socket check to verify proxy host and port responsiveness."""
        host = proxy_data.get("host")
        port = proxy_data.get("port")
        if not host or not port:
            return False
        try:
            with socket.create_connection((str(host), int(port)), timeout=timeout):
                return True
        except (OSError, TimeoutError):
            return False

    def run(self) -> None:
        """Executes browser launch sequence on worker thread."""
        self.signals.started.emit()

        if self.daemon_supervisor:
            try:
                self.daemon_supervisor.ensure_running()
            except Exception as de:
                logger.warning("Daemon supervisor check warning: %s", de)

        success_count = 0
        total_count = len(self.profile_ids)

        for profile_id in self.profile_ids:
            if self._cancelled:
                logger.info("Orbita launch cancelled early.")
                break

            p = self.profile_repo.get_by_id(profile_id)
            if not p:
                continue

            name = p.get("name", f"Profile #{profile_id}")
            self.signals.profile_started.emit(profile_id, name)

            proxy = self.proxy_repo.get_by_id(p["proxy_id"]) if p.get("proxy_id") else None

            # Auto-rotate proxy if rotating proxy has change_ip_url
            if proxy and (proxy.get("proxy_type") == "rotating" or proxy.get("change_ip_url")) and self.proxy_service:
                try:
                    self.proxy_service.change_rotating_ip(proxy["id"])
                except Exception as re_err:
                    logger.debug("Auto rotate proxy notice for profile %d: %s", profile_id, re_err)

            # Pre-launch Proxy Guard (fail closed): never open a profile without a usable proxy/VPN,
            # unless the user explicitly chose direct mode (host IP) for this profile.
            refusal = None
            direct = bool(p.get("direct_connection")) and not proxy and not p.get("vpn_config")
            if not proxy and not p.get("vpn_config") and not direct:
                refusal = "Chưa gán proxy/VPN: chặn mở trình duyệt để bảo vệ IP máy thật. Nếu cố ý chạy bằng IP máy: chuột phải hồ sơ → Quản Lý Proxy & Mạng → Chạy không proxy (dùng IP máy)"
            elif proxy and proxy.get("status") == "leak_detected":
                refusal = f"Proxy #{proxy.get('id')} bị gắn cờ LEAK DETECTED: chặn mở trình duyệt"
            elif proxy and not self._check_proxy_alive(proxy):
                refusal = f"Proxy {proxy.get('host')}:{proxy.get('port')} không phản hồi: chưa mở trình duyệt"
            if refusal:
                logger.warning("Launch refused for profile '%s': %s", name, refusal)
                self.signals.profile_failed.emit(profile_id, name, refusal)
                continue
            if direct:
                logger.warning("Profile '%s' launched WITHOUT proxy (direct mode chosen by user)", name)

            try:
                uuid_val = p.get("uuid")
                debugger_addr = None
                if uuid_val and self.orbita_launcher:
                    try:
                        debugger_addr = self.orbita_launcher.launch_via_gologin_sdk(
                            profile_id=uuid_val,
                            proxy_data=proxy,
                            headless=False,
                            sync=False,
                            db_profile_id=profile_id,
                            direct_connection=direct,
                            cookie_raw=p.get("cookies_json") or p.get("cookie") or p.get("cookies_browser"),
                        )
                    except Exception as sdk_err:
                        logger.warning(
                            "GoLogin SDK launch failed for %s, falling back to direct binary: %s",
                            uuid_val,
                            sdk_err,
                        )

                if debugger_addr:
                    success_count += 1
                    self.signals.profile_launched.emit(profile_id, name, str(debugger_addr))
                elif self.orbita_launcher:
                    proc = self.orbita_launcher.launch_profile(p, proxy)
                    if proc and getattr(proc, "pid", None):
                        success_count += 1
                        self.signals.profile_launched.emit(profile_id, name, f"PID:{proc.pid}")
                    else:
                        self.signals.profile_failed.emit(profile_id, name, "Process execution returned null")
                else:
                    self.signals.profile_failed.emit(profile_id, name, "No launcher configured")
            except Exception as e:
                logger.error("Launch orbita failed for profile %d: %s", profile_id, e)
                self.signals.profile_failed.emit(profile_id, name, str(e))

        self.signals.batch_completed.emit(success_count, total_count)
        self.signals.finished.emit()
