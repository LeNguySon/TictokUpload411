"""
Orbita Antidetect Browser Launcher integrating GoLogin Orbita profiles with fingerprint isolation.
Follows ANTIDETECT_MASTER_SPEC: C++ proxy Preferences injection, WebRTC protection, and pre-launch sanitization.
"""

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from src.infrastructure.browser.process_supervisor import BrowserProcessSupervisor

logger = logging.getLogger(__name__)


class OrbitaLauncher:
    """
    Manages discovery and launching of Orbita Antidetect Browser with custom flags,
    native C++ proxy authentication routing via Preferences, and fingerprint noise injection.
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

    DAEMON_PROFILES_DIR = Path(r"D:\SamMonnygocLiengXiPoker\SamMonnygocLiengXiPoker\profiles")

    def __init__(self, executable_path: str | Path | None = None) -> None:
        self.executable_path = Path(executable_path) if executable_path else self._find_browser_executable()
        self._active_processes: dict[int, subprocess.Popen] = {}
        self._active_profile_dirs: dict[int, Path] = {}
        self.vpn_bridges: dict[Any, Any] = {}
        self.supervisor = BrowserProcessSupervisor()

    def _find_browser_executable(self) -> Path:
        for p in self.DEFAULT_ORBITA_PATHS:
            if p.exists() and p.is_file():
                return p
        return Path("chrome.exe")

    def prepare_profile_environment(
        self,
        user_data_dir: str | Path,
        profile_data: dict[str, Any],
        proxy_data: dict[str, Any] | None = None,
    ) -> Path:
        """
        Performs pre-launch lock sanitization and injects full antidetect & proxy
        settings into Default/Preferences according to ANTIDETECT_MASTER_SPEC.
        """
        p_dir = Path(user_data_dir).resolve()
        p_dir.mkdir(parents=True, exist_ok=True)

        # 1. Pre-launch Sanitization: wipe stale singleton locks and sync data
        lock_files = [
            "SingletonLock",
            "SingletonSocket",
            "SingletonCookie",
            "RunningChromeVersion",
        ]
        for lock in lock_files:
            lock_path = p_dir / lock
            if lock_path.exists():
                try:
                    if lock_path.is_file():
                        lock_path.unlink(missing_ok=True)
                except Exception as e:
                    logger.warning("Could not delete lock file %s: %s", lock_path, e)

        sync_data_dir = p_dir / "Default" / "Sync Data"
        if sync_data_dir.exists():
            try:
                shutil.rmtree(sync_data_dir, ignore_errors=True)
            except Exception as e:
                logger.warning("Could not remove Sync Data dir: %s", e)

        # 2. Inject or Update Default/Preferences
        default_dir = p_dir / "Default"
        default_dir.mkdir(parents=True, exist_ok=True)
        pref_path = default_dir / "Preferences"

        pref_data: dict[str, Any] = {}
        if pref_path.exists():
            try:
                pref_data = json.loads(pref_path.read_text(encoding="utf-8"))
            except Exception:
                pref_data = {}

        pref_data.setdefault("profile", {})["exit_type"] = "Normal"
        pref_data.setdefault("signin", {})["allowed"] = False
        pref_data.setdefault("sync", {})["requested"] = False

        gologin = pref_data.setdefault("gologin", {})
        gologin["name"] = profile_data.get("name", "Default")
        gologin["profile_id"] = str(profile_data.get("uuid") or profile_data.get("id", "profile_1"))
        gologin["screenWidth"] = profile_data.get("screen_width", 1920)
        gologin["screenHeight"] = profile_data.get("screen_height", 1080)
        gologin["userAgent"] = (
            profile_data.get("user_agent")
            or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
        )
        gologin["navigator"] = {"platform": "Win32", "max_touch_points": 0}
        gologin["canvasMode"] = "noise"
        gologin["canvasNoise"] = float(profile_data.get("canvas_noise", 8.751249))
        gologin["audioContext"] = {"enable": True, "noiseValue": 5.793972911028913e-7}
        gologin["clientRects"] = {"mode": "noise", "noise": 2.14810925182}
        gologin["client_rects_noise_enable"] = True
        gologin["getClientRectsNoice"] = 2.14810925182
        gologin["get_client_rects_noise"] = 2.14810925182

        vendor = profile_data.get("webgl_vendor") or "Google Inc. (NVIDIA)"
        renderer = (
            profile_data.get("webgl_renderer")
            or "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"
        )
        gologin["webgl"] = {"metadata": {"vendor": vendor, "renderer": renderer, "mode": True}}
        gologin["webGl"] = {"vendor": vendor, "renderer": renderer, "mode": True}
        gologin["webgl_noice_enable"] = True
        gologin["webglNoiceEnable"] = True
        gologin["webgl_noise_enable"] = True
        gologin["webgl_noise_value"] = 91.240581
        gologin["webglNoiseValue"] = 91.240581

        gologin["mediaDevices"] = {
            "enable": True,
            "uid": "e8046704b3cb45338099e2261bc1be67a1b2",
            "audioInputs": 1,
            "audioOutputs": 1,
            "videoInputs": 1,
        }
        gologin["webrtc"] = {
            "enable": False,
            "mode": "disabled",
            "should_fill_empty_ice_list": True,
        }
        gologin["hardwareConcurrency"] = int(profile_data.get("cpu_cores", 8))
        gologin["deviceMemory"] = int(profile_data.get("memory_gb", 8)) * 1024
        gologin["doNotTrack"] = False

        # Align Timezone, Geolocation, and Languages with proxy/profile geolocation
        timezone_id = (
            profile_data.get("timezone_id")
            or (proxy_data.get("timezone") if proxy_data else None)
            or "America/New_York"
        )
        gologin["timezone"] = {"id": timezone_id}

        lat = profile_data.get("latitude") or (proxy_data.get("latitude") if proxy_data else None) or 40.7128
        lon = profile_data.get("longitude") or (proxy_data.get("longitude") if proxy_data else None) or -74.0060
        gologin["geoLocation"] = {
            "latitude": float(lat),
            "longitude": float(lon),
            "accuracy": 10,
        }

        country = (profile_data.get("country") or (proxy_data.get("country") if proxy_data else None) or "US").upper()
        if country == "US":
            gologin["languages"] = "en-US,en"
            gologin["langHeader"] = "en-US,en;q=0.9"
        elif country == "VN":
            gologin["languages"] = "vi-VN,vi,en-US,en"
            gologin["langHeader"] = "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7"
        else:
            lang_code = country.lower()
            gologin["languages"] = f"en-{country},{lang_code},en"
            gologin["langHeader"] = f"en-{country},{lang_code};q=0.9,en;q=0.8"

        # Proxy Configuration Injection
        if proxy_data and proxy_data.get("host") and proxy_data.get("port"):
            proto = str(proxy_data.get("protocol") or "http").lower()
            host = proxy_data["host"]
            port = proxy_data["port"]
            user = proxy_data.get("username")
            pwd = proxy_data.get("password")
            if user and pwd:
                server_uri = f"{proto}://{user}:{pwd}@{host}:{port}"
                gologin["proxy"] = {
                    "mode": "fixed_servers",
                    "server": server_uri,
                    "username": user,
                    "password": pwd,
                    "schema": proto,
                }
            else:
                server_uri = f"{proto}://{host}:{port}"
                gologin["proxy"] = {
                    "mode": "fixed_servers",
                    "server": server_uri,
                    "schema": proto,
                }
        else:
            gologin["proxy"] = {"mode": "none"}

        try:
            pref_path.write_text(json.dumps(pref_data, indent=2), encoding="utf-8")
        except Exception as pe:
            logger.warning("Failed to write Preferences file to %s: %s", pref_path, pe)

        return p_dir

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
        """
        Constructs Chromium command line arguments enforcing fingerprint, isolation boundaries,
        and WebRTC leak prevention. Enforces --user-data-dir as the terminal parameter.
        """
        resolved_data_dir = Path(user_data_dir).resolve()
        args = [
            str(self.executable_path),
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-encryption",
            "--font-masking-mode=1",
            "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
            "--disable-ipv6",
            "--password-store=basic",
            "--disable-blink-features=AutomationControlled,WebGPU",
            f"--fingerprint-canvas-noise={canvas_noise}",
        ]

        if proxy_uri:
            # Strip credentials if embedded in uri because chromium flag expects host:port
            clean_proxy = proxy_uri
            proxy_host = None
            if "@" in proxy_uri:
                scheme, rest = proxy_uri.split("://", 1)
                _, host_port = rest.split("@", 1)
                clean_proxy = f"{scheme}://{host_port}"
                proxy_host = host_port.split(":")[0]
            elif "://" in proxy_uri:
                rest = proxy_uri.split("://", 1)[1]
                proxy_host = rest.split(":")[0]
            else:
                proxy_host = proxy_uri.split(":")[0]

            args.append(f"--proxy-server={clean_proxy}")
            if proxy_host:
                args.append(f'--host-resolver-rules="MAP * 0.0.0.0 , EXCLUDE {proxy_host}"')
            args.append("--enforce-webrtc-ip-permission-check")

        if user_agent:
            args.append(f"--user-agent={user_agent}")

        if webgl_vendor:
            args.append(f"--webgl-vendor={webgl_vendor}")
        if webgl_renderer:
            args.append(f"--webgl-renderer={webgl_renderer}")

        args.append(start_url)
        # Spec requirement: --user-data-dir MUST always be the final parameter
        args.append(f"--user-data-dir={resolved_data_dir}")
        return args

    def launch_profile(
        self,
        profile_data: dict[str, Any],
        proxy_data: dict[str, Any] | None = None,
        start_url: str = "https://www.tiktok.com",
    ) -> subprocess.Popen:
        """Launches the Orbita browser process asynchronously without blocking GUI thread."""
        # WireGuard VPN Userspace Bridge integration: route via local SOCKS5 if configured
        if profile_data.get("vpn_config") and not proxy_data:
            try:
                from src.infrastructure.vpn.vpn_bridge import UserspaceVpnBridge
                from src.infrastructure.vpn.wireguard_manager import WireGuardConfig

                wg_cfg = WireGuardConfig.from_conf(
                    profile_data["vpn_config"],
                    name=f"wg_{profile_data.get('id', 'default')}",
                )
                p_id_key = profile_data.get("id", "default")
                bridge = UserspaceVpnBridge(
                    profile_id=p_id_key,
                    config=wg_cfg,
                    mock_mode=True,
                )
                bridge.start()
                self.vpn_bridges[p_id_key] = bridge
                proxy_data = bridge.as_proxy_dict()
            except Exception as ve:
                logger.warning("Could not initialize VPN bridge: %s", ve)

        storage_dir = profile_data.get("storage_dir") or f"profiles/{profile_data.get('name', 'default')}"
        p_dir = self.prepare_profile_environment(storage_dir, profile_data, proxy_data)

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
            self._active_profile_dirs[profile_id] = p_dir

        if proc and proc.pid:
            self.supervisor.create_lock(p_dir, pid=proc.pid)

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
                self.supervisor.shutdown_process_tree(proc.pid)
                closed = True
            except Exception as e:
                logger.warning("Error terminating process for profile %s: %s", p_id, e)
                try:
                    proc.kill()
                    closed = True
                except Exception:
                    pass

        # Remove lock file
        if p_id is not None and p_id in self._active_profile_dirs:
            p_dir = self._active_profile_dirs.pop(p_id)
            self.supervisor.remove_lock(p_dir)
        elif isinstance(profile_data, dict):
            s_dir = profile_data.get("storage_dir")
            if s_dir:
                self.supervisor.remove_lock(Path(s_dir))

        # 3. Stop Userspace VPN Bridge if associated with this profile
        if p_id is not None and p_id in self.vpn_bridges:
            try:
                bridge = self.vpn_bridges.pop(p_id)
                bridge.stop()
                closed = True
            except Exception as e:
                logger.warning("Error stopping VPN bridge for profile %s: %s", p_id, e)

        return closed

    def sync_daemon_profile_proxy(
        self,
        profile_uuid: str,
        proxy_data: dict[str, Any] | None,
    ) -> None:
        """Synchronizes assigned proxy directly to SamMonny daemon profile's Preferences."""
        daemon_profile_dir = self.DAEMON_PROFILES_DIR / profile_uuid
        if daemon_profile_dir.exists():
            pref_path = daemon_profile_dir / "Default" / "Preferences"
            if pref_path.exists():
                try:
                    data = json.loads(pref_path.read_text(encoding="utf-8"))
                    gologin = data.setdefault("gologin", {})
                    if proxy_data and proxy_data.get("host") and proxy_data.get("port"):
                        proto = str(proxy_data.get("protocol") or "http").lower()
                        host = proxy_data["host"]
                        port = proxy_data["port"]
                        user = proxy_data.get("username")
                        pwd = proxy_data.get("password")
                        if user and pwd:
                            gologin["proxy"] = {
                                "mode": "fixed_servers",
                                "server": f"{proto}://{user}:{pwd}@{host}:{port}",
                                "username": user,
                                "password": pwd,
                                "schema": proto,
                            }
                        else:
                            gologin["proxy"] = {
                                "mode": "fixed_servers",
                                "server": f"{proto}://{host}:{port}",
                                "schema": proto,
                            }
                    else:
                        gologin["proxy"] = {"mode": "none"}

                    pref_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                    logger.info("Successfully updated daemon profile proxy Preferences for %s", profile_uuid)
                except Exception as e:
                    logger.warning("Failed to update daemon profile proxy for %s: %s", profile_uuid, e)

    def launch_via_gologin_sdk(
        self,
        profile_id: str,
        proxy_data: dict[str, Any] | None = None,
        headless: bool = False,
        sync: bool = False,
        port: int = 36912,
    ) -> str:
        """
        Launches profile through SamMonny GoLogin SDK compatibility layer.
        Ensures proxy is synchronized to Preferences prior to starting.
        Returns debugger address (e.g. '127.0.0.1:port').
        """
        if proxy_data:
            self.sync_daemon_profile_proxy(profile_id, proxy_data)

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

    def is_profile_running(self, profile_data_or_id: dict[str, Any] | int) -> bool:
        """
        Determines whether a profile is actively running in the OS.
        Checks:
        1. In-memory subprocess Popen (poll() is None).
        2. Supervisor lock file inspection for profile directory.
        """
        p_id = profile_data_or_id if isinstance(profile_data_or_id, int) else profile_data_or_id.get("id")

        # 1. Check in-memory active process
        if p_id is not None and p_id in self._active_processes:
            proc = self._active_processes[p_id]
            if proc.poll() is None:
                return True
            else:
                # Process has terminated, clean up stale reference
                self._active_processes.pop(p_id, None)

        # 2. Check active profile directory lock via supervisor
        if p_id is not None and p_id in self._active_profile_dirs:
            p_dir = self._active_profile_dirs[p_id]
            if self.supervisor.is_process_running(p_dir):
                return True

        if isinstance(profile_data_or_id, dict):
            s_dir = profile_data_or_id.get("storage_dir")
            if s_dir and self.supervisor.is_process_running(Path(s_dir)):
                return True

            uuid_val = profile_data_or_id.get("uuid")
            if uuid_val:
                daemon_dir = self.DAEMON_PROFILES_DIR / str(uuid_val)
                if daemon_dir.exists() and self.supervisor.is_process_running(daemon_dir):
                    return True

        return False
