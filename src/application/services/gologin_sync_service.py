"""
GoLogin Profile Synchronization & Lifecycle Service.
Coordinates between SamMonny GoLogin SDK and internal ProfileRepository.
"""

from __future__ import annotations

import logging
from typing import Any

from src.infrastructure.browser.sammonny_daemon_manager import SamMonnyDaemonSupervisor
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository

logger = logging.getLogger(__name__)


class GoLoginSyncService:
    """
    Manages synchronization and creation of authentic GoLogin / Orbita profiles
    with Bayesian Antidetect Fingerprints in TAVM.
    """

    def __init__(
        self,
        profile_repo: ProfileRepository,
        project_repo: ProjectRepository,
        proxy_repo: ProxyRepository | None = None,
        daemon_supervisor: SamMonnyDaemonSupervisor | None = None,
    ) -> None:
        self.profile_repo = profile_repo
        self.project_repo = project_repo
        self.proxy_repo = proxy_repo
        self.daemon_supervisor = daemon_supervisor or SamMonnyDaemonSupervisor()

    def sync_from_local_gologin(self, port: int = 36912) -> int:
        """
        Fetches all profiles from SamMonny GoLogin SDK daemon and synchronizes them into local database.
        Returns the number of profiles successfully synchronized.
        """
        self.daemon_supervisor.ensure_daemon_running()

        from sammonny.gologin.gologin import GoLogin

        try:
            gl = GoLogin({"port": port})
            raw_profiles = gl.get_profiles()
            return self.sync_profiles_list(raw_profiles)
        except Exception as e:
            logger.error("Failed to sync profiles from GoLogin SDK: %s", e)
            return 0

    def sync_profiles_list(self, raw_profiles: list[dict[str, Any]]) -> int:
        """
        Parses raw profile dictionary items from GoLogin / SamMonny daemon
        and upserts them into ProfileRepository.
        """
        synced_count = 0
        default_proj = self.project_repo.get_default_project()
        default_proj_id = default_proj["id"] if default_proj else 1

        for raw in raw_profiles:
            uuid_val = raw.get("id")
            if not uuid_val:
                continue

            name = raw.get("name") or f"GoLogin_{uuid_val[:8]}"
            notes = raw.get("notes") or ""
            fp = raw.get("fingerprint") or {}
            nav = fp.get("navigator") or {}
            webgl = fp.get("webgl") or {}
            screen = fp.get("screen") or {}
            tz = fp.get("timezone") or {}

            user_agent = nav.get("user_agent") or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/152.0.0.0"
            canvas_noise = float(fp.get("canvas_noise") or 8.0)
            audio_noise = float(fp.get("audio_noise") or 0.0001)
            webgl_vendor = webgl.get("vendor") or "Google Inc. (Intel)"
            webgl_renderer = webgl.get("renderer") or "ANGLE (Intel)"
            res_w = screen.get("width") or 1920
            res_h = screen.get("height") or 1080
            resolution = f"{res_w}x{res_h}"
            cpu_cores = int(nav.get("hardware_concurrency") or 4)
            memory_gb = int(nav.get("device_memory") or 8)
            timezone_id = tz.get("timezone_id") or "America/New_York"

            existing = self.profile_repo.get_by_uuid(uuid_val)
            profile_payload = {
                "uuid": uuid_val,
                "name": name,
                "project_id": default_proj_id,
                "storage_dir": f"profiles/{uuid_val}",
                "status": "stopped",
                "user_agent": user_agent,
                "os_type": fp.get("os", "win"),
                "resolution": resolution,
                "cpu_cores": cpu_cores,
                "memory_gb": memory_gb,
                "canvas_noise": canvas_noise,
                "audio_noise": audio_noise,
                "webgl_vendor": webgl_vendor,
                "webgl_renderer": webgl_renderer,
                "timezone_id": timezone_id,
                "notes": notes,
            }

            if existing:
                self.profile_repo.update(existing["id"], profile_payload)
            else:
                self.profile_repo.create(profile_payload)

            synced_count += 1

        logger.info("Successfully synchronized %d GoLogin profiles into database.", synced_count)
        return synced_count

    def create_real_gologin_profile(
        self,
        name: str,
        project_id: int | None = None,
        proxy_id: int | None = None,
        cookie: str | None = None,
        port: int = 36912,
    ) -> int:
        """
        Creates an authentic profile via SamMonny GoLogin SDK with Bayesian Antidetect Fingerprint,
        and records it into ProfileRepository. Returns created local profile ID.
        """
        self.daemon_supervisor.ensure_daemon_running()

        from sammonny.gologin.gologin import GoLogin

        gl = GoLogin({"port": port})
        create_payload: dict[str, Any] = {"name": name, "os": "win"}

        # Attach proxy configuration if provided
        if proxy_id and self.proxy_repo:
            px = self.proxy_repo.get_by_id(proxy_id)
            if px and px.get("host") and px.get("port"):
                create_payload["proxy"] = {
                    "mode": px.get("protocol", "http"),
                    "host": px["host"],
                    "port": px["port"],
                    "username": px.get("username"),
                    "password": px.get("password"),
                }

        # 1. Create on GoLogin Daemon
        gologin_uuid = gl.create(create_payload)
        logger.info("GoLogin SDK created profile UUID: %s", gologin_uuid)

        # 2. Inject cookies if provided
        if cookie:
            try:
                from sammonny.core.models import CookieItem

                items = [CookieItem(name="sessionid", value=cookie, domain=".tiktok.com", path="/")]
                gl.post_cookies(items, profile_id=gologin_uuid)
            except Exception as ce:
                logger.warning("Could not post initial cookie via GoLogin SDK: %s", ce)

        # 3. Store record into local repository
        profile_data = {
            "uuid": gologin_uuid,
            "name": name,
            "project_id": project_id,
            "proxy_id": proxy_id,
            "storage_dir": f"profiles/{gologin_uuid}",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/152.0.0.0",
            "status": "LIVE" if cookie else "stopped",
            "canvas_noise": 8.0,
            "audio_noise": 0.0001,
            "webgl_vendor": "Google Inc. (Intel)",
            "webgl_renderer": "ANGLE (Intel, Intel(R) UHD Graphics Direct3D11)",
            "cookie": cookie if cookie else None,
        }

        return self.profile_repo.create(profile_data)
