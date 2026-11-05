"""
Browser Cookie Injector supporting structured cookie parsing and injection into GoLogin & Orbita profiles.
Clean Architecture: Infrastructure Layer (Browser).
"""

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Common HTTP-only cookie names in TikTok session authentication
_HTTP_ONLY_COOKIES = {
    "sessionid",
    "sessionid_ss",
    "sid_tt",
    "sid_guard",
    "ssid_guard",
    "passport_csrf_token",
    "passport_csrf_token_default",
    "uid_tt",
    "uid_tt_ss",
}


class BrowserCookieInjector:
    """
    Engine responsible for converting raw TikTok cookies into Chromium-compatible CookieItem objects
    and injecting them into the profile's GoLogin Daemon and SQLite storage.
    """

    @classmethod
    def parse_cookie_string(
        cls,
        cookie_raw: str,
        domain: str = ".tiktok.com",
    ) -> list[dict[str, Any]]:
        """
        Parses either a JSON array of cookie dicts or a standard HTTP Cookie header string
        into structured dictionary format required by Chromium & GoLogin SDK.
        """
        if not cookie_raw or not cookie_raw.strip():
            return []

        raw = cookie_raw.strip()

        # 1. Try parsing JSON format (e.g. from Cookie-Editor extension)
        if raw.startswith("[") and raw.endswith("]"):
            try:
                items = json.loads(raw)
                if isinstance(items, list):
                    parsed_list: list[dict[str, Any]] = []
                    for it in items:
                        if isinstance(it, dict) and it.get("name"):
                            c_domain = it.get("domain") or domain
                            if not c_domain.startswith("."):
                                c_domain = f".{c_domain}"
                            c_name = str(it["name"]).strip()
                            parsed_list.append(
                                {
                                    "name": c_name,
                                    "value": str(it.get("value", "")),
                                    "domain": c_domain,
                                    "path": str(it.get("path", "/")),
                                    "secure": bool(it.get("secure", True)),
                                    "httpOnly": bool(
                                        it.get("httpOnly")
                                        if it.get("httpOnly") is not None
                                        else (c_name.lower() in _HTTP_ONLY_COOKIES)
                                    ),
                                    "sameSite": str(it.get("sameSite", "Lax")),
                                    "expirationDate": it.get("expirationDate") or (time.time() + 31536000),
                                }
                            )
                    if parsed_list:
                        return parsed_list
            except Exception as e:
                logger.debug("Failed parsing cookie as JSON, falling back to key-value string: %s", e)

        # 2. Key-Value semicolon separated string format
        result: list[dict[str, Any]] = []
        pairs = [p.strip() for p in raw.split(";") if "=" in p]
        for p in pairs:
            k, _, v = p.partition("=")
            k = k.strip()
            v = v.strip()
            if not k:
                continue
            is_http_only = k.lower() in _HTTP_ONLY_COOKIES
            result.append(
                {
                    "name": k,
                    "value": v,
                    "domain": domain,
                    "path": "/",
                    "secure": True,
                    "httpOnly": is_http_only,
                    "sameSite": "Lax",
                    "expirationDate": time.time() + 31536000,
                }
            )

        return result

    @classmethod
    def inject_to_gologin(
        cls,
        profile_uuid: str,
        cookie_raw: str,
        gl_instance: Any = None,
        port: int = 36912,
    ) -> bool:
        """
        Injects cookies into GoLogin daemon profile via SamMonny GoLogin SDK.
        """
        cookie_items = cls.parse_cookie_string(cookie_raw, domain=".tiktok.com")
        if not cookie_items:
            return True

        try:
            if gl_instance is None:
                from sammonny.gologin.gologin import GoLogin

                gl_instance = GoLogin({"port": port})

            success = gl_instance.post_cookies(cookie_items, profile_id=profile_uuid)
            logger.info(
                "Successfully posted %d cookies to GoLogin profile %s: %s", len(cookie_items), profile_uuid, success
            )
            return bool(success)
        except Exception as e:
            logger.warning("Error injecting cookies via GoLogin SDK for %s: %s", profile_uuid, e)
            return False

    @classmethod
    def inject_to_chromium_sqlite(
        cls,
        storage_dir: str | Path,
        cookie_raw: str,
        domain: str = ".tiktok.com",
    ) -> bool:
        """
        Injects cookies directly into local Chromium Network/Cookies SQLite file if available.
        """
        cookie_items = cls.parse_cookie_string(cookie_raw, domain=domain)
        if not cookie_items:
            return True

        p_dir = Path(storage_dir)
        # Search candidate paths for Cookies database
        candidate_paths = [
            p_dir / "Default" / "Network" / "Cookies",
            p_dir / "Network" / "Cookies",
            p_dir / "Default" / "Cookies",
            p_dir / "Cookies",
        ]

        target_db: Path | None = None
        for cand in candidate_paths:
            if cand.is_file():
                target_db = cand
                break

        if not target_db:
            return False

        try:
            now_epoch = int(time.time())
            expires_utc = (now_epoch + 31536000) * 1000000 + 11644473600000000  # Chrome microsecond timestamp

            with sqlite3.connect(str(target_db)) as conn:
                cur = conn.cursor()
                # Inspect schema to check columns
                col_info = cur.execute("PRAGMA table_info(cookies);").fetchall()
                if not col_info:
                    return False
                col_names = {r[1] for r in col_info}

                for c in cookie_items:
                    k = c["name"]
                    v = c["value"]
                    d = c["domain"]
                    p = c["path"]
                    sec = 1 if c.get("secure") else 0
                    httponly = 1 if c.get("httpOnly") else 0

                    if "host_key" in col_names:
                        cur.execute(
                            """
                            INSERT OR REPLACE INTO cookies
                            (creation_utc, host_key, top_frame_site_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly, last_access_utc, has_expires, is_persistent, priority, samesite, source_scheme, source_port, is_same_party)
                            VALUES (?, ?, '', ?, ?, X'', ?, ?, ?, ?, ?, 1, 1, 1, 1, 2, 443, 0);
                            """,
                            (now_epoch * 1000000, d, k, v, p, expires_utc, sec, httponly, now_epoch * 1000000),
                        )
                conn.commit()
                logger.info("Successfully injected %d cookies directly to SQLite DB: %s", len(cookie_items), target_db)
                return True
        except Exception as e:
            logger.debug("Could not write direct cookies into SQLite %s: %s", target_db, e)
            return False
