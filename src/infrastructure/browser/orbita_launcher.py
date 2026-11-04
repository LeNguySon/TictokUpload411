"""
Orbita Antidetect Browser Launcher integrating GoLogin Orbita profiles with fingerprint isolation.
"""

import logging
import os
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class OrbitaLauncher:
    """
    Manages discovery and launching of Orbita Antidetect Browser with custom flags,
    proxy authentication routing, and fingerprint noise injection.
    """

    DEFAULT_ORBITA_PATHS = [
        Path(r"C:\Users\sonson\Desktop\Gloglin2609\resources\engines\orbita-152\chrome.exe"),
        Path(r"C:\Users\sonson\Desktop\Gloglin2609\resources\engines\orbita-139\chrome.exe"),
        Path(r"C:\Users\sonson\Desktop\Gloglin2609\resources\engines\orbita-123\chrome.exe"),
        Path(os.environ.get("USERPROFILE", "C:/Users/sonson")) / ".gologin/browser/orbita-browser-130/chrome.exe",
        Path(os.environ.get("USERPROFILE", "C:/Users/sonson")) / ".gologin/browser/orbita-browser-128/chrome.exe",
        Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
        Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
    ]

    def __init__(self, executable_path: str | Path | None = None) -> None:
        self.executable_path = Path(executable_path) if executable_path else self._find_browser_executable()
        self._active_processes: dict[int, subprocess.Popen] = {}

    def _find_browser_executable(self) -> Path:
        for p in self.DEFAULT_ORBITA_PATHS:
            if p.exists() and p.is_file():
                return p
        return Path("chrome.exe")

    def build_launch_args(
        self,
        user_data_dir: str | Path,
        proxy_uri: str | None = None,
        user_agent: str | None = None,
        canvas_noise: float = 8.0,
        webgl_vendor: str | None = None,
        webgl_renderer: str | None = None,
        start_url: str = "https://www.tiktok.com",
    ) -> list[str]:
        """Constructs Chromium command line arguments enforcing fingerprint and isolation boundaries."""
        args = [
            str(self.executable_path),
            f"--user-data-dir={Path(user_data_dir).resolve()}",
            "--no-first-run",
            "--no-default-browser-check",
            "--password-store=basic",
            f"--fingerprint-canvas-noise={canvas_noise}",
        ]

        if proxy_uri:
            # Strip credentials if embedded in uri because chromium flag expects host:port
            # Format: http://user:pass@host:port -> http://host:port
            clean_proxy = proxy_uri
            if "@" in proxy_uri:
                scheme, rest = proxy_uri.split("://", 1)
                _, host_port = rest.split("@", 1)
                clean_proxy = f"{scheme}://{host_port}"
            args.append(f"--proxy-server={clean_proxy}")

        if user_agent:
            args.append(f"--user-agent={user_agent}")

        if webgl_vendor:
            args.append(f"--webgl-vendor={webgl_vendor}")
        if webgl_renderer:
            args.append(f"--webgl-renderer={webgl_renderer}")

        args.append(start_url)
        return args

    def launch_profile(
        self,
        profile_data: dict[str, Any],
        proxy_data: dict[str, Any] | None = None,
        start_url: str = "https://www.tiktok.com",
    ) -> subprocess.Popen:
        """Launches the Orbita browser process asynchronously without blocking GUI thread."""
        storage_dir = profile_data.get("storage_dir") or f"profiles/{profile_data.get('name', 'default')}"
        p_dir = Path(storage_dir).resolve()
        p_dir.mkdir(parents=True, exist_ok=True)

        proxy_uri = None
        if proxy_data:
            scheme = proxy_data.get("protocol", "http")
            host = proxy_data.get("host")
            port = proxy_data.get("port")
            usr = proxy_data.get("username")
            pwd = proxy_data.get("password")
            auth = f"{usr}:{pwd}@" if usr and pwd else ""
            if host and port:
                proxy_uri = f"{scheme}://{auth}{host}:{port}"

        args = self.build_launch_args(
            user_data_dir=p_dir,
            proxy_uri=proxy_uri,
            user_agent=profile_data.get("user_agent"),
            canvas_noise=profile_data.get("canvas_noise", 8.0),
            webgl_vendor=profile_data.get("webgl_vendor"),
            webgl_renderer=profile_data.get("webgl_renderer"),
            start_url=start_url,
        )

        logger.info("Launching Orbita browser for profile: %s with args: %s", profile_data.get("name"), args)
        proc = subprocess.Popen(args, shell=False)
        profile_id = profile_data.get("id")
        if profile_id is not None:
            self._active_processes[profile_id] = proc
        return proc

    def close_profile(self, profile_data: dict[str, Any] | int) -> bool:
        """Closes browser process and GoLogin session for a specific profile."""
        if isinstance(profile_data, int):
            p_id = profile_data
            uuid_val = None
        else:
            p_id = profile_data.get("id")
            uuid_val = profile_data.get("uuid")

        closed = False
        # 1. Stop via GoLogin SDK if UUID available
        if uuid_val:
            try:
                self.stop_via_gologin_sdk(str(uuid_val))
                closed = True
            except Exception as e:
                logger.warning("Error stopping via GoLogin SDK for %s: %s", uuid_val, e)

        # 2. Terminate tracked subprocess Popen if active
        if p_id is not None and p_id in self._active_processes:
            proc = self._active_processes.pop(p_id)
            try:
                proc.terminate()
                closed = True
            except Exception as e:
                logger.warning("Error terminating process for profile %s: %s", p_id, e)
                try:
                    proc.kill()
                    closed = True
                except Exception:
                    pass

        return closed

    def launch_via_gologin_sdk(
        self,
        profile_id: str,
        headless: bool = False,
        sync: bool = False,
        port: int = 36912,
    ) -> str:
        """
        Launches profile through SamMonny GoLogin SDK compatibility layer.
        Returns debugger address (e.g. '127.0.0.1:port').
        """
        from sammonny.gologin.gologin import GoLogin

        gl = GoLogin({"profile_id": profile_id, "port": port, "sync": sync, "headless": headless})
        debugger_address = gl.start()
        logger.info("GoLogin SDK launched profile %s at debugger address %s", profile_id, debugger_address)
        return debugger_address

    def stop_via_gologin_sdk(self, profile_id: str, port: int = 36912) -> bool:
        """Stops profile session through SamMonny GoLogin SDK."""
        from sammonny.gologin.gologin import GoLogin

        gl = GoLogin({"profile_id": profile_id, "port": port})
        return gl.stop()
