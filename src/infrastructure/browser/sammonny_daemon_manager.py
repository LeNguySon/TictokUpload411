"""
SamMonny Native Daemon Supervisor for Windows 11.
Manages automatic discovery, health checks, background lifecycle, and port binding
for SamMonny Daemon (port 7654) and GoLogin SDK Daemon (port 36912).
"""

from __future__ import annotations

import atexit
import json
import logging
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SamMonnyDaemonSupervisor:
    """
    Supervisor managing the local sammonny-daemon process ensuring ports 7654 and 36912
    are alive and responding for the SamMonny Antidetect SDK.
    """

    CANDIDATE_BINARY_PATHS = [
        Path(
            r"D:\SamMonnygocLiengXiPoker\SamMonnygocLiengXiPoker\dist_standalone\sammonny-antidetect\bin\sammonny-daemon.exe"
        ),
        Path(r"D:\SamMonnygocLiengXiPoker\dist_standalone\sammonny-antidetect\bin\sammonny-daemon.exe"),
        Path(r"C:\SamMonny\bin\sammonny-daemon.exe"),
    ]

    CANDIDATE_WORKING_DIRS = [
        Path(r"D:\SamMonnygocLiengXiPoker\SamMonnygocLiengXiPoker"),
        Path(r"D:\SamMonnygocLiengXiPoker"),
    ]

    def __init__(
        self,
        internal_port: int = 7654,
        sdk_port: int = 36912,
        auto_register_atexit: bool = True,
    ) -> None:
        self.internal_port = internal_port
        self.sdk_port = sdk_port
        self._spawned_process: subprocess.Popen | None = None

        if auto_register_atexit:
            atexit.register(self.shutdown)

    def find_daemon_binary(self) -> Path | None:
        """Finds the sammonny-daemon.exe binary on the host system."""
        for p in self.CANDIDATE_BINARY_PATHS:
            if p.exists() and p.is_file():
                return p
        return None

    def find_working_dir(self) -> Path:
        """Finds the root working directory containing gologin.db and profiles."""
        for p in self.CANDIDATE_WORKING_DIRS:
            if p.exists() and p.is_dir():
                return p
        return Path.cwd()

    def check_health(self) -> dict[str, Any]:
        """Checks if ports 7654 and 36912 are alive and healthy."""
        result: dict[str, Any] = {"daemon_7654": False, "sdk_36912": False}

        # Check internal daemon (7654)
        try:
            url_7654 = f"http://127.0.0.1:{self.internal_port}/health"
            req = urllib.request.Request(url_7654, headers={"User-Agent": "TAVM-Supervisor/1.0"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.getcode() == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    result["daemon_7654"] = True
                    result["info_7654"] = data
        except Exception:
            pass

        # Check GoLogin SDK port (36912)
        try:
            url_36912 = f"http://127.0.0.1:{self.sdk_port}/service/check-server"
            req = urllib.request.Request(url_36912, headers={"User-Agent": "TAVM-Supervisor/1.0"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.getcode() == 200:
                    result["sdk_36912"] = True
        except Exception:
            pass

        return result

    def is_running(self) -> bool:
        """Returns True if at least the internal daemon or SDK port is responding."""
        status = self.check_health()
        return bool(status["daemon_7654"] or status["sdk_36912"])

    def ensure_daemon_running(self, timeout_sec: float = 6.0) -> bool:
        """
        Verifies if daemon is running; if not, launches sammonny-daemon.exe in background
        and waits until it becomes healthy.
        """
        if self.is_running():
            logger.info("SamMonny Daemon is already active on ports %d / %d", self.internal_port, self.sdk_port)
            return True

        binary_path = self.find_daemon_binary()
        if not binary_path:
            logger.error("Cannot start SamMonny Daemon: binary 'sammonny-daemon.exe' not found.")
            return False

        working_dir = self.find_working_dir()
        cmd = [
            str(binary_path),
            "serve",
            "--port",
            str(self.internal_port),
            "--sdk-port",
            str(self.sdk_port),
        ]

        logger.info("Starting SamMonny Daemon: %s (cwd=%s)", cmd, working_dir)

        # Windows-specific: hide console window
        creationflags = 0
        try:
            creationflags = subprocess.CREATE_NO_WINDOW
        except AttributeError:
            pass

        try:
            self._spawned_process = subprocess.Popen(
                cmd,
                cwd=str(working_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        except Exception as e:
            logger.error("Failed to spawn sammonny-daemon: %s", e)
            return False

        # Wait until ports respond
        start_time = time.time()
        while time.time() - start_time < timeout_sec:
            if self.is_running():
                logger.info("SamMonny Daemon successfully started and verified healthy.")
                return True
            time.sleep(0.3)

        logger.warning("SamMonny Daemon launched but timed out waiting for health check.")
        return False

    def shutdown(self) -> None:
        """Terminates the spawned daemon process cleanly if launched by this supervisor."""
        if self._spawned_process is not None:
            try:
                logger.info("Terminating spawned SamMonny Daemon PID: %d", self._spawned_process.pid)
                self._spawned_process.terminate()
                self._spawned_process.wait(timeout=2.0)
            except Exception:
                try:
                    self._spawned_process.kill()
                except Exception:
                    pass
            finally:
                self._spawned_process = None
