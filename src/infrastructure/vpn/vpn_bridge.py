"""
Userspace WireGuard VPN Bridge per profile.
Routes profile traffic through an isolated local SOCKS5 proxy endpoint (127.0.0.1:port)
without altering operating system network adapters or system routing tables.
"""

from __future__ import annotations

import logging
import os
import platform
import socket
import subprocess
import time
from enum import StrEnum
from pathlib import Path
from typing import Any, Self

from src.infrastructure.vpn.wireguard_manager import WireGuardConfig

logger = logging.getLogger(__name__)
IS_WINDOWS = platform.system() == "Windows"


class VpnBridgeState(StrEnum):
    """Lifecycle state of the VPN Bridge."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"


class UserspaceVpnBridge:
    """Manages an isolated WireGuard -> Local SOCKS5 bridge per profile."""

    def __init__(
        self,
        profile_id: int | str,
        config: WireGuardConfig,
        local_port: int | None = None,
        binary_path: Path | str | None = None,
        mock_mode: bool = False,
    ) -> None:
        self.profile_id = profile_id
        self.config = config
        self._custom_port = local_port
        self.local_port: int | None = None
        self.binary_path = Path(binary_path) if binary_path else None
        self.mock_mode = mock_mode

        self.state = VpnBridgeState.STOPPED
        self._process: subprocess.Popen[Any] | None = None
        self._mock_server: socket.socket | None = None

    @property
    def is_running(self) -> bool:
        """Indicates whether the VPN bridge is actively running."""
        return self.state == VpnBridgeState.RUNNING

    @staticmethod
    def find_free_port() -> int:
        """Finds an available ephemeral TCP port on 127.0.0.1."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return int(s.getsockname()[1])

    def start(self, timeout: float = 5.0) -> int:
        """
        Starts the VPN bridge and returns the allocated local SOCKS5 port.
        """
        if self.is_running:
            if self.local_port is not None:
                return self.local_port
            raise RuntimeError(f"Bridge already running on port {self.local_port}")

        self.state = VpnBridgeState.STARTING
        port = self._custom_port or self.find_free_port()

        if self.mock_mode:
            # Mock mode: bind and reserve port, simulating running daemon
            try:
                self._mock_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._mock_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self._mock_server.bind(("127.0.0.1", port))
                self._mock_server.listen(1)
                self._mock_server.close()
                self._mock_server = None
            except Exception as e:
                logger.debug("Port check warning in mock mode: %s", e)

            self.local_port = port
            self.state = VpnBridgeState.RUNNING
            logger.info(
                "VPN Bridge started in mock mode on 127.0.0.1:%s (profile %s)",
                port,
                self.profile_id,
            )
            return port

        # Real process launch
        if not self.binary_path or not self.binary_path.is_file():
            self.state = VpnBridgeState.ERROR
            raise FileNotFoundError(f"VPN Bridge daemon binary not found: {self.binary_path}")

        temp_dir = Path(os.environ.get("TEMP", "C:/Temp")) if IS_WINDOWS else Path("/tmp")
        tmp_conf = temp_dir / f"wg_{self.profile_id}.conf"
        tmp_conf.write_text(self.config.to_conf(), encoding="utf-8")

        cmd = [
            str(self.binary_path),
            "--config",
            str(tmp_conf),
            "--socks-port",
            str(port),
            "--bind",
            "127.0.0.1",
        ]

        try:
            # DEVNULL: the pipes were never read, so a chatty daemon would block once they filled up.
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            deadline = time.monotonic() + timeout
            ready = False
            while time.monotonic() < deadline:
                if self._check_port_open("127.0.0.1", port):
                    ready = True
                    break
                time.sleep(0.1)

            if not ready:
                self.stop()
                self.state = VpnBridgeState.ERROR
                raise TimeoutError(f"VPN Bridge failed to open port {port} within {timeout}s")

            self.local_port = port
            self.state = VpnBridgeState.RUNNING
            return port

        except Exception as exc:
            self.stop()
            self.state = VpnBridgeState.ERROR
            logger.error("Failed to start VPN Bridge: %s", exc)
            raise
        finally:
            # The config holds the WireGuard PrivateKey: the daemon has read it once the port is open
            # (or start failed), so it must not stay in %TEMP%.
            try:
                tmp_conf.unlink(missing_ok=True)
            except OSError as e:
                logger.warning("Could not remove WireGuard temp config %s: %s", tmp_conf, e)

    def stop(self) -> None:
        """Stops the bridge and ensures spawned processes are terminated."""
        if self._mock_server:
            try:
                self._mock_server.close()
            except Exception:
                pass
            self._mock_server = None

        if self._process is not None:
            try:
                self._process.terminate()
                self._process.wait(timeout=1.0)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None

        self.local_port = None
        self.state = VpnBridgeState.STOPPED
        logger.info("VPN Bridge stopped for profile %s", self.profile_id)

    def get_proxy_endpoint(self) -> dict[str, Any]:
        """Returns the local proxy endpoint information for this bridge."""
        if not self.is_running or not self.local_port:
            raise RuntimeError("Cannot get proxy endpoint while bridge is not running")
        return {
            "protocol": "socks5",
            "host": "127.0.0.1",
            "port": self.local_port,
        }

    def as_proxy_dict(self) -> dict[str, Any]:
        """Formats as a proxy dictionary compatible with Orbita launcher."""
        if not self.is_running or not self.local_port:
            raise RuntimeError("Cannot format proxy dict while bridge is not running")
        return {
            "host": "127.0.0.1",
            "port": self.local_port,
            "protocol": "socks5",
            "username": None,
            "password": None,
        }

    @staticmethod
    def _check_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
        """Checks if a TCP port is accepting connections."""
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except (OSError, TimeoutError):
            return False

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(self, *_args: Any) -> None:
        self.stop()
