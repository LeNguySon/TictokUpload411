"""
GoLogin Profile Synchronization & Lifecycle Service.
Coordinates between SamMonny GoLogin SDK and internal ProfileRepository.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.infrastructure.browser.sammonny_daemon_manager import SamMonnyDaemonSupervisor
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.project_repository import ProjectRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository

logger = logging.getLogger(__name__)



def _daemon_fingerprint(gl: Any, profile_uuid: str) -> dict[str, Any] | None:
    """The fingerprint the daemon generated for ``profile_uuid`` (None if its record cannot be read)."""
    try:
        info = gl.client.get_profile(profile_uuid)
        fp = (getattr(info, "raw_data", None) or {}).get("fingerprint")
    except Exception as e:
        logger.warning("Daemon fingerprint of %s unavailable (%s): a local one is generated", profile_uuid, e)
        return None
    return fp if isinstance(fp, dict) and fp.get("navigator") else None


def backfill_fingerprints(profile_repo: Any, daemon_client: Any | None) -> dict[str, int]:
    """Gives every profile without a stored fingerprint its own fixed one: the daemon's record when it has one
    (the browser already launches with it), otherwise a unique one derived from the profile uuid.
    Network + DB work: run it off the GUI thread. Returns {"daemon": n, "generated": m}."""
    from src.domain.fingerprint.browser_fingerprint import generate_fingerprint, profile_columns

    counts = {"daemon": 0, "generated": 0}
    for profile in profile_repo.list_all():
        if profile.get("fingerprint_json") or not profile.get("uuid"):
            continue
        fp = None
        if daemon_client is not None:
            try:
                info = daemon_client.get_profile(profile["uuid"])
                raw_fp = (getattr(info, "raw_data", None) or {}).get("fingerprint") if info else None
                fp = raw_fp if isinstance(raw_fp, dict) and raw_fp.get("navigator") else None
            except Exception as e:
                logger.debug("Daemon record of %s unavailable: %s", profile["uuid"], e)
        source = "daemon" if fp else "generated"
        fp = fp or generate_fingerprint(str(profile["uuid"]))
        profile_repo.update(profile["id"], profile_columns(fp))
        counts[source] += 1
    if counts["daemon"] or counts["generated"]:
        logger.info("Fingerprints assigned: %d from daemon records, %d generated", counts["daemon"], counts["generated"])
    return counts


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
            if fp.get("navigator"):
                profile_payload["fingerprint_json"] = json.dumps(fp, ensure_ascii=False, sort_keys=True)

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
        extra_fields: dict[str, Any] | None = None,
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
        daemon_fp = _daemon_fingerprint(gl, gologin_uuid)

        # 2. Inject cookies if provided
        if cookie:
            try:
                from src.infrastructure.browser.cookie_injector import BrowserCookieInjector

                BrowserCookieInjector.inject_to_gologin(
                    profile_uuid=gologin_uuid,
                    cookie_raw=cookie,
                    gl_instance=gl,
                    port=port,
                )
            except Exception as ce:
                logger.warning("Could not post initial cookie via GoLogin SDK: %s", ce)

        # 3. Resolve physical profile directory and inject direct Chromium SQLite cookies
        from src.infrastructure.browser.orbita_launcher import OrbitaLauncher

        prof_dir = OrbitaLauncher.resolve_profile_dir({"uuid": gologin_uuid, "name": name})
        prof_dir.mkdir(parents=True, exist_ok=True)
        if cookie:
            try:
                from src.infrastructure.browser.cookie_injector import BrowserCookieInjector

                BrowserCookieInjector.seed_profile_cookies(prof_dir, cookie)
            except Exception as se:
                logger.warning("Could not inject sqlite cookies into %s: %s", prof_dir, se)

        # 4. Store record into local repository
        profile_data = {
            "uuid": gologin_uuid,
            "name": name,
            "project_id": project_id,
            "proxy_id": proxy_id,
            "storage_dir": str(prof_dir),
            "status": "LIVE" if cookie else "stopped",
            "cookie": cookie if cookie else None,
        }

        if daemon_fp:
            # Store the daemon's own fingerprint: app and daemon then apply the same one at every launch.
            profile_data["fingerprint_json"] = json.dumps(daemon_fp, ensure_ascii=False, sort_keys=True)

        if extra_fields:
            for k, v in extra_fields.items():
                if v is not None and k not in profile_data:
                    profile_data[k] = v

        return self.profile_repo.create(profile_data)
