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
                                    # Real expiry of exported cookies (it was replaced by "+1 year").
                                    "expirationDate": it.get("expirationDate") or it.get("expires") or None,
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
    def ensure_chromium_cookies_db(cls, db_path: Path) -> None:
        """
        Creates Chromium Cookies SQLite database with schema version 24 if it does not already exist.
        """
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key LONGVARCHAR NOT NULL UNIQUE PRIMARY KEY,
                    value LONGVARCHAR
                );
                """
            )
            cur.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('version', '24');")
            cur.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('last_compatible_version', '24');")
            cur.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('mmap_status', '-1');")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS cookies (
                    creation_utc INTEGER NOT NULL,
                    host_key TEXT NOT NULL,
                    top_frame_site_key TEXT NOT NULL,
                    name TEXT NOT NULL,
                    value TEXT NOT NULL,
                    encrypted_value BLOB NOT NULL,
                    path TEXT NOT NULL,
                    expires_utc INTEGER NOT NULL,
                    is_secure INTEGER NOT NULL,
                    is_httponly INTEGER NOT NULL,
                    last_access_utc INTEGER NOT NULL,
                    has_expires INTEGER NOT NULL,
                    is_persistent INTEGER NOT NULL,
                    priority INTEGER NOT NULL,
                    samesite INTEGER NOT NULL,
                    source_scheme INTEGER NOT NULL,
                    source_port INTEGER NOT NULL,
                    last_update_utc INTEGER NOT NULL,
                    source_type INTEGER NOT NULL,
                    has_cross_site_ancestor INTEGER NOT NULL,
                    PRIMARY KEY (host_key, top_frame_site_key, name, path, source_type, has_cross_site_ancestor)
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    SEED_MARKER = "tavm_cookie_seed.sha256"

    @classmethod
    def session_expiry(cls, cookie_raw: str) -> float | None:
        """Expiry (unix) of the session cookie in a JSON export; None for header strings / unknown."""
        if not cookie_raw:
            return None
        try:
            plain = cls._plain_cookie(cookie_raw).strip()
        except Exception:
            return None
        if not plain.startswith("["):
            return None
        best: float | None = None
        for c in cls.parse_cookie_string(plain):
            exp = c.get("expirationDate")
            if c.get("name") in ("sessionid", "sessionid_ss", "sid_tt") and exp:
                best = max(best or 0.0, float(exp))
        return best

    @classmethod
    def _plain_cookie(cls, cookie_raw: str) -> str:
        if isinstance(cookie_raw, str) and cookie_raw.startswith("gloglin:dpapi:v1:"):
            from src.infrastructure.credentials.dpapi import unprotect_text

            return unprotect_text(cookie_raw) or ""
        return str(cookie_raw or "")

    @classmethod
    def seed_profile_cookies(cls, profile_dir: str | Path, cookie_raw: str | None) -> bool:
        """Writes the user's imported cookies into the profile ONCE per distinct cookie value.

        After that the browser owns its cookie jar: re-writing the imported cookies on every launch
        (INSERT OR REPLACE) overwrote the session the browser had refreshed and could log the account
        out. A changed cookie value (user edited/re-imported the cookies) is applied once again.
        The marker holds only a SHA-256 of the cookie, never the cookie itself.
        Returns True when cookies were written now.
        """
        if not cookie_raw or not str(cookie_raw).strip():
            return False
        import hashlib

        try:
            plain = cls._plain_cookie(cookie_raw).strip()
        except Exception as exc:
            logger.warning("Could not read protected cookies for seeding: %s", exc)
            return False
        if not plain:
            return False
        digest = hashlib.sha256(plain.encode("utf-8")).hexdigest()
        marker = Path(profile_dir) / cls.SEED_MARKER
        try:
            if marker.read_text(encoding="utf-8").strip() == digest:
                return False
        except OSError:
            pass
        if not cls.inject_to_chromium_sqlite(profile_dir, plain):
            return False
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(digest, encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not write cookie seed marker in %s: %s", profile_dir, exc)
        return True

    @classmethod
    def inject_to_chromium_sqlite(
        cls,
        storage_dir: str | Path,
        cookie_raw: str,
        domain: str = ".tiktok.com",
    ) -> bool:
        """
        Injects cookies directly into local Chromium Network/Cookies SQLite file.
        Automatically unprotects DPAPI envelopes and creates the Cookies DB schema if missing.
        """
        if not cookie_raw or not str(cookie_raw).strip():
            return True

        # AgentShield: Automatically unprotect DPAPI ciphertext if present
        plain_cookie_raw = cookie_raw
        if isinstance(cookie_raw, str) and cookie_raw.startswith("gloglin:dpapi:v1:"):
            try:
                from src.infrastructure.credentials.dpapi import unprotect_text

                unwrapped = unprotect_text(cookie_raw)
                if unwrapped:
                    plain_cookie_raw = unwrapped
            except Exception as e:
                logger.warning("Could not unprotect DPAPI cookie envelope: %s", e)

        cookie_items = cls.parse_cookie_string(plain_cookie_raw, domain=domain)
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

        # If DB does not exist, initialize Default/Network/Cookies with schema v24
        if not target_db:
            target_db = p_dir / "Default" / "Network" / "Cookies"
            try:
                cls.ensure_chromium_cookies_db(target_db)
            except Exception as dbe:
                logger.error("Failed to initialize Chromium cookies SQLite database at %s: %s", target_db, dbe)
                return False

        conn: sqlite3.Connection | None = None
        try:
            now_epoch = int(time.time())
            # Header strings carry no expiry: TikTok sets the real one on the first request.
            default_expires_utc = (now_epoch + 31536000) * 1000000 + 11644473600000000

            conn = sqlite3.connect(str(target_db))
            cur = conn.cursor()
            col_info = cur.execute("PRAGMA table_info(cookies);").fetchall()
            if not col_info:
                return False
            col_names = {r[1] for r in col_info}

            for c in cookie_items:
                exp_unix = c.get("expirationDate")
                if exp_unix is not None and 0 < float(exp_unix) <= now_epoch:
                    continue  # already expired: never hand a dead cookie to the browser
                expires_utc = (
                    int(float(exp_unix) * 1000000) + 11644473600000000
                    if exp_unix and float(exp_unix) > 0
                    else default_expires_utc
                )
                k = c["name"]
                v = c["value"]
                d = c["domain"]
                p = c["path"]
                sec = 1 if c.get("secure") else 0
                httponly = 1 if c.get("httpOnly") else 0

                if "host_key" in col_names:
                    # Construct insert parameters compatible with both newer v24 and legacy schema
                    cols = [
                        "creation_utc",
                        "host_key",
                        "top_frame_site_key",
                        "name",
                        "value",
                        "encrypted_value",
                        "path",
                        "expires_utc",
                        "is_secure",
                        "is_httponly",
                        "last_access_utc",
                        "has_expires",
                        "is_persistent",
                        "priority",
                        "samesite",
                        "source_scheme",
                        "source_port",
                    ]
                    vals = [
                        now_epoch * 1000000,
                        d,
                        "",
                        k,
                        v,
                        sqlite3.Binary(b""),
                        p,
                        expires_utc,
                        sec,
                        httponly,
                        now_epoch * 1000000,
                        1,
                        1,
                        1,
                        1,
                        2,
                        443,
                    ]

                    if "last_update_utc" in col_names:
                        cols.append("last_update_utc")
                        vals.append(now_epoch * 1000000)
                    if "source_type" in col_names:
                        cols.append("source_type")
                        vals.append(0)
                    if "has_cross_site_ancestor" in col_names:
                        cols.append("has_cross_site_ancestor")
                        vals.append(0)
                    if "is_same_party" in col_names:
                        cols.append("is_same_party")
                        vals.append(0)

                    placeholders = ", ".join("?" for _ in cols)
                    col_str = ", ".join(cols)
                    cur.execute(
                        f"INSERT OR REPLACE INTO cookies ({col_str}) VALUES ({placeholders});",
                        tuple(vals),
                    )
            conn.commit()
            logger.info("Successfully injected %d cookies directly to SQLite DB: %s", len(cookie_items), target_db)
            return True
        except Exception as e:
            logger.debug("Could not write direct cookies into SQLite %s: %s", target_db, e)
            return False
        finally:
            if conn:
                try:
                    conn.close()
                except Exception as ignored:
                    logger.debug("inject_to_chromium_sqlite: ignored error: %s", ignored)
