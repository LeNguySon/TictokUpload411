"""
Passive TikTok Synchronization Service.
Coordinates 3-tier passive extraction:
1. Offline SQLite Cookie Extraction (SamMonny LDAP FileTime decoding).
2. Live DOM Hydration Extraction (__UNIVERSAL_DATA_FOR_REHYDRATION__ through proxy).
3. Live CDP Network Sniffing integration.
Updates SQLite profiles table and emits UI signals without requiring OAuth tokens.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.application.signals.app_signals import AppSignalBus
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
from src.infrastructure.tiktok.dom_hydration_extractor import TikTokDomHydrationExtractor
from src.infrastructure.tiktok.network_sniffer import TikTokNetworkSniffer

logger = logging.getLogger(__name__)

# Chromium epoch offset: microseconds between 1601-01-01 and 1970-01-01 (SamMonny SDK standard)
CHROMIUM_EPOCH_OFFSET_MICROS = 11644473600000000
WINDOWS_EPOCH_DELTA = 11644473600

CORE_COOKIES = [
    "sessionid",
    "sessionid_ss",
    "sid_tt",
    "sid_guard",
    "uid_tt",
    "tt_chain_token",
    "passport_csrf_token",
    "ttwid",
    "store-idc",
]


class PassiveTikTokSyncService:
    """
    Coordinates passive telemetry extraction across offline cookies, public DOM hydration,
    and live CDP network payloads for managed TikTok MMO profiles.
    """

    def __init__(
        self,
        profile_repo: ProfileRepository,
        proxy_repo: ProxyRepository | None = None,
        sniffer: TikTokNetworkSniffer | None = None,
        extractor: TikTokDomHydrationExtractor | None = None,
        signal_bus: AppSignalBus | None = None,
    ) -> None:
        self.profile_repo = profile_repo
        self.proxy_repo = proxy_repo
        self.sniffer = sniffer or TikTokNetworkSniffer(
            db_path=profile_repo.db_path if hasattr(profile_repo, "db_path") else None
        )
        self.extractor = extractor or TikTokDomHydrationExtractor()
        self.signal_bus = signal_bus or AppSignalBus.instance()

    def sync_profile_offline_cookies(self, profile_id: int) -> dict[str, Any]:
        """
        Reads Chromium SQLite cookie database directly from profile storage dir.
        Determines sessionid validity and updates state_loggin_browser (LIVE / DIE).
        """
        row = self.profile_repo.get_by_id(profile_id)
        if not row:
            return {"ok": False, "is_live": False, "cookies": {}}

        storage_dir = row.get("storage_dir") or f"profiles/{row.get('name', 'default')}"
        p_dir = Path(storage_dir).resolve()

        cookie_candidates = [
            p_dir / "Default" / "Network" / "Cookies",
            p_dir / "Network" / "Cookies",
            p_dir / "Default" / "Cookies",
            p_dir / "Cookies",
        ]

        target_db: Path | None = None
        for cand in cookie_candidates:
            if cand.exists() and cand.is_file():
                target_db = cand
                break

        if not target_db:
            logger.debug("No SQLite cookie database found for profile %s at %s", profile_id, p_dir)
            return {"ok": False, "is_live": False, "cookies": {}}

        cookies_found: dict[str, str] = {}
        is_live = False
        now_ts = time.time()

        try:
            # Connect in read-only mode to prevent database locks
            conn = sqlite3.connect(f"file:{target_db.as_posix()}?mode=ro", uri=True)
            cursor = conn.cursor()
            rows = cursor.execute(
                """
                SELECT name, value, expires_utc FROM cookies
                WHERE host_key LIKE '%tiktok.com%' OR host_key LIKE '%.tiktok.com';
                """
            ).fetchall()
            conn.close()

            for name, val, expires_utc in rows:
                if not name:
                    continue
                # Calculate expiry from Windows LDAP FileTime using microsecond epoch offset
                is_expired = False
                if expires_utc > 0:
                    if expires_utc > CHROMIUM_EPOCH_OFFSET_MICROS:
                        unix_exp = (expires_utc - CHROMIUM_EPOCH_OFFSET_MICROS) / 1_000_000.0
                    else:
                        unix_exp = float(expires_utc)
                    if unix_exp < now_ts:
                        is_expired = True

                if not is_expired and val:
                    cookies_found[str(name)] = str(val)

            # CSRF equivalence: if tt_csrf_token is present and passport_csrf_token is missing
            if "tt_csrf_token" in cookies_found and "passport_csrf_token" not in cookies_found:
                cookies_found["passport_csrf_token"] = cookies_found["tt_csrf_token"]

            # Check core authentication token
            if "sessionid" in cookies_found or "sessionid_ss" in cookies_found:
                is_live = True

            login_state = 1 if is_live else 0
            new_status = "LIVE" if is_live else "DIE"

            updates = {
                "state_loggin_browser": login_state,
                "status": new_status,
                "cookies_json": json.dumps(cookies_found),
            }
            self.profile_repo.update(profile_id, **updates)
            if self.signal_bus:
                self.signal_bus.profile_updated.emit(profile_id, updates)
            logger.info(
                "Offline cookie sync for profile %s: is_live=%s (found %d cookies)",
                profile_id,
                is_live,
                len(cookies_found),
            )
            return {"ok": True, "is_live": is_live, "cookies": cookies_found}

        except Exception as e:
            logger.warning("Error reading offline SQLite cookies for profile %s: %s", profile_id, e)
            return {"ok": False, "is_live": False, "cookies": {}}

    def sync_profile_dom_hydration(
        self,
        profile_id: int,
        html: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Extracts channel statistics from public HTML or fetches it through proxy.
        Updates followers, following, likes, videos, nickname, bio, and country.
        """
        row = self.profile_repo.get_by_id(profile_id)
        if not row:
            return None

        username = row.get("username_on_tiktok") or row.get("name")
        if not username:
            return None

        # Clean username
        clean_user = username.lstrip("@").strip()
        if not clean_user:
            return None

        page_html = html
        if not page_html:
            # Fetch public channel HTML through profile's proxy if assigned
            url = f"https://www.tiktok.com/@{clean_user}"
            try:
                page_html = self._fetch_url_content(url, row.get("proxy_id"))
            except Exception as fe:
                logger.debug("Could not fetch public HTML for @%s: %s", clean_user, fe)
                return None

        if not page_html:
            return None

        hydration = self.extractor.extract(page_html)
        if not hydration:
            return None

        now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        updates: dict[str, Any] = {}

        if hydration.get("followerCount") is not None:
            updates["total_followers"] = hydration["followerCount"]
        if hydration.get("followingCount") is not None:
            updates["total_following"] = hydration["followingCount"]
        if hydration.get("heartCount") is not None:
            updates["total_likes"] = hydration["heartCount"]
        if hydration.get("videoCount") is not None:
            updates["total_videos"] = hydration["videoCount"]
        if hydration.get("nickname"):
            updates["nickname"] = hydration["nickname"]
        if hydration.get("avatarUrl"):
            updates["avatar_url"] = hydration["avatarUrl"]
        if hydration.get("signature"):
            updates["bio"] = hydration["signature"]
        if hydration.get("region"):
            updates["country"] = hydration["region"]
        if hydration.get("privacy") is not None:
            updates["privacy"] = hydration["privacy"]

        if updates:
            updates["statistic_date_update"] = now_str
            self.profile_repo.update(profile_id, **updates)
            logger.info("DOM Hydration synced %d fields for profile %s (@%s)", len(updates), profile_id, clean_user)

        return hydration

    def _fetch_url_content(self, url: str, proxy_id: int | None) -> str:
        """Fetches URL content routing through the assigned proxy if present."""
        if proxy_id and self.proxy_repo:
            px = self.proxy_repo.get_by_id(proxy_id)
            if px and px.get("status") == "leak_detected":
                logger.warning("Proxy %s is flagged with LEAK DETECTED! Aborting DOM scraping.", proxy_id)
                return ""

        opener = urllib.request.build_opener()
        if proxy_id and self.proxy_repo:
            px = self.proxy_repo.get_by_id(proxy_id)
            if px and px.get("host") and px.get("port"):
                proto = px.get("protocol", "http")
                host = px["host"]
                port = px["port"]
                usr = px.get("username")
                pwd = px.get("password")
                auth = f"{usr}:{pwd}@" if usr and pwd else ""
                proxy_url = f"{proto}://{auth}{host}:{port}"
                handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
                opener = urllib.request.build_opener(handler)

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        try:
            with opener.open(req, timeout=5.0) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            logger.debug("Failed to fetch DOM content for %s: %s", url, e)
            return ""

    def sync_single_profile(self, profile_id: int) -> dict[str, Any]:
        """
        Orchestrates complete passive synchronization for a single profile:
        1. Checks offline SQLite cookies for LIVE/DIE and session validity.
        2. Pulls public DOM hydration metrics through proxy if username is known.
        3. Emits profile_updated signal to refresh UI.
        """
        # 1. Offline Cookie Check
        cookie_res = self.sync_profile_offline_cookies(profile_id)

        # 2. DOM Hydration Check
        dom_res = None
        try:
            dom_res = self.sync_profile_dom_hydration(profile_id)
        except Exception as de:
            logger.debug("DOM hydration check error on profile %s: %s", profile_id, de)

        # 3. Pull latest row from DB to compile complete update payload
        row = self.profile_repo.get_by_id(profile_id) or {}

        # 4. Emit signal to GUI
        if self.signal_bus:
            self.signal_bus.profile_updated.emit(profile_id, row)

        return {
            "profile_id": profile_id,
            "status": row.get("status", "DIE"),
            "state_loggin_browser": row.get("state_loggin_browser", 0),
            "total_followers": row.get("total_followers", 0),
            "total_likes": row.get("total_likes", 0),
            "total_videos": row.get("total_videos", 0),
            "money_earned": row.get("money_earned", 0.0),
            "rpm": row.get("rpm", 0.0),
            "balance": row.get("balance", 0.0),
            "cookies_count": len(cookie_res.get("cookies", {})),
            "dom_synced": bool(dom_res),
        }
