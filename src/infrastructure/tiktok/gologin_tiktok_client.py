"""GoLogin TikTok Client.
Integrates GoLogin / Orbita SDK with AgentShield DPAPI Vault and Proxy Routing.
Ensures every TikTok API request (Passport, Moderation, Appeals, Creator Rewards)
runs through the authentic profile proxy, TLS Chrome fingerprint, and secure session cookies.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from src.infrastructure.credentials.dpapi import unprotect_text

logger = logging.getLogger(__name__)


def parse_cookies_to_header(cookies_raw: Any) -> str:
    """Parses various cookie representations (JSON list, dict, DPAPI envelope) to Cookie header string."""
    if not cookies_raw:
        return ""
    if isinstance(cookies_raw, str):
        cookies_str = cookies_raw.strip()
        if cookies_str.startswith("gloglin:dpapi:v1:"):
            try:
                unprotected = unprotect_text(cookies_str)
                if unprotected:
                    cookies_str = unprotected.strip()
            except Exception:
                pass
        if cookies_str.startswith("[") or cookies_str.startswith("{"):
            try:
                parsed = json.loads(cookies_str)
                return parse_cookies_to_header(parsed)
            except Exception:
                return cookies_str
        return cookies_str
    elif isinstance(cookies_raw, list):
        pairs = []
        for c in cookies_raw:
            if isinstance(c, dict) and "name" in c and "value" in c:
                pairs.append(f"{c['name']}={c['value']}")
        return "; ".join(pairs)
    elif isinstance(cookies_raw, dict):
        return "; ".join(f"{k}={v}" for k, v in cookies_raw.items())
    return ""


def extract_cookie_val(cookie_header: str, cookie_name: str) -> str | None:
    """Extracts a specific cookie value from a 'name=val; name2=val2' header string."""
    for pair in cookie_header.split(";"):
        parts = pair.strip().split("=", 1)
        if len(parts) == 2 and parts[0].strip() == cookie_name:
            return parts[1].strip()
    return None


class GoLoginTikTokClient:
    """Enterprise client managing authentic TikTok HTTP requests through GoLogin profile configuration."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path or "data/app.db")

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_profile_cookie_header(self, profile_id: int) -> str:
        """Retrieves and decrypts the Cookie header for the given profile."""
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT uuid, cookies_json, cookies_browser FROM profiles WHERE id=?", (profile_id,)
            ).fetchone()
            if not row:
                return ""
            p = dict(row)
            raw = p.get("cookies_browser") or p.get("cookies_json") or ""
            header = parse_cookies_to_header(raw)
            if not header and p.get("uuid"):
                # Fallback to GoLogin SDK daemon if available
                try:
                    from sammonny.gologin.gologin import GoLogin

                    gl = GoLogin({"profile_id": p["uuid"]})
                    gl_cookies = gl.get_cookies()
                    if gl_cookies:
                        header = parse_cookies_to_header(gl_cookies)
                except Exception:
                    pass
            return header
        finally:
            conn.close()

    def get_profile_proxy(self, profile_id: int) -> dict[str, Any] | None:
        """Retrieves assigned proxy configuration for the given profile."""
        conn = self._get_connection()
        try:
            p_row = conn.execute("SELECT proxy_id FROM profiles WHERE id=?", (profile_id,)).fetchone()
            if not p_row or not p_row["proxy_id"]:
                return None
            proxy_id = p_row["proxy_id"]
            px_row = conn.execute("SELECT * FROM proxies WHERE id=?", (proxy_id,)).fetchone()
            if not px_row:
                return None
            return dict(px_row)
        finally:
            conn.close()

    def _build_proxy_url(self, proxy_dict: dict[str, Any] | None) -> str | None:
        if not proxy_dict or not proxy_dict.get("host") or not proxy_dict.get("port"):
            return None
        proto = proxy_dict.get("protocol", "http")
        host = proxy_dict["host"]
        port = proxy_dict["port"]
        u = proxy_dict.get("username")
        p = proxy_dict.get("password")
        auth = f"{u}:{p}@" if u and p else ""
        return f"{proto}://{auth}{host}:{port}"

    def request_api(
        self,
        profile_id: int,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        json_data: Any = None,
        data: Any = None,
        timeout: int = 15,
    ) -> dict[str, Any]:
        """Executes HTTP request routed through GoLogin proxy and TLS fingerprint."""
        from curl_cffi import requests

        conn = self._get_connection()
        try:
            row = conn.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
            if not row:
                return {"status_code": -1, "error": "Profile not found"}
            p = dict(row)
        finally:
            conn.close()

        cookie_hdr = self.get_profile_cookie_header(profile_id)
        proxy_dict = self.get_profile_proxy(profile_id)
        proxy_url = self._build_proxy_url(proxy_dict)
        proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None

        req_headers = {
            "User-Agent": p.get("user_agent")
            or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Cookie": cookie_hdr,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        }
        csrf = extract_cookie_val(cookie_hdr, "passport_csrf_token") or extract_cookie_val(cookie_hdr, "tt_csrf_token")
        if csrf:
            req_headers["x-secsdk-csrf-token"] = csrf

        if headers:
            req_headers.update(headers)

        try:
            resp = requests.request(
                method,
                url,
                headers=req_headers,
                json=json_data,
                data=data,
                proxies=proxies,
                impersonate="chrome120",
                timeout=timeout,
            )
            try:
                res_json = resp.json()
                if isinstance(res_json, dict):
                    res_json["_status_code"] = resp.status_code
                    return res_json
                return {"data": res_json, "_status_code": resp.status_code}
            except Exception:
                return {"_status_code": resp.status_code, "text": resp.text}
        except Exception as e:
            logger.debug("GoLogin TikTok Client request failed for %s: %s", url, e)
            return {"status_code": -1, "error": str(e)}

    def verify_session(self, profile_id: int) -> dict[str, Any]:
        """Queries /passport/web/account/info/ using the profile's dedicated proxy and GoLogin session."""
        url = "https://www.tiktok.com/passport/web/account/info/"
        res = self.request_api(profile_id, url, method="GET")

        if res.get("status_code") == -1:
            return {"is_live": False, "error": res.get("error", "Network failure")}

        data = res.get("data") if isinstance(res.get("data"), dict) else {}
        msg = res.get("message")
        if msg == "success" and data.get("username"):
            return {
                "is_live": True,
                "username": data.get("username"),
                "user_id": str(data.get("user_id") or data.get("user_id_str") or ""),
                "nickname": data.get("screen_name") or data.get("username"),
                "email": data.get("email"),
                "avatar_url": data.get("avatar_url"),
                "status_code": res.get("_status_code", 200),
            }

        desc = data.get("description") or "Session expired"
        return {
            "is_live": False,
            "error": desc,
            "status_code": res.get("_status_code", 401),
        }
