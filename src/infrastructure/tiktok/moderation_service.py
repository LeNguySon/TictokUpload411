"""
TikTok Moderation Service.
Interacts with official TikTok Creator Center Moderation Endpoints:
- Account standing & community guideline strikes (/api/creator/account/standing/)
- Video guideline violations, originality strikes, and sound copyright (/api/creator/violation/list/)
Learned from Gloglin2609/engine/tiktok/moderation_service.py with strict parity.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def parse_cookie_header_str(cookies_data: Any) -> str:
    """Parses various cookie representations into a valid HTTP Cookie header string."""
    if not cookies_data:
        return ""
    if isinstance(cookies_data, str):
        cookies_str = cookies_data.strip()
        if cookies_str.startswith("[") or cookies_str.startswith("{"):
            try:
                parsed = json.loads(cookies_str)
                return parse_cookie_header_str(parsed)
            except Exception:
                return cookies_str
        return cookies_str
    elif isinstance(cookies_data, list):
        pairs = []
        for c in cookies_data:
            if isinstance(c, dict) and "name" in c and "value" in c:
                pairs.append(f"{c['name']}={c['value']}")
        return "; ".join(pairs)
    elif isinstance(cookies_data, dict):
        return "; ".join(f"{k}={v}" for k, v in cookies_data.items())
    return ""


class TikTokModerationService:
    """Service for querying and persisting TikTok channel health, strikes, and video violations."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path or "data/app.db")

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _request_tiktok_api(
        self,
        url: str,
        cookie_header: str,
        user_agent: str,
        proxy_dict: dict[str, Any] | None = None,
        timeout: int = 15,
    ) -> dict[str, Any]:
        """Executes HTTP request impersonating Chrome 120 TLS fingerprint via curl_cffi."""
        try:
            from curl_cffi import requests

            headers = {
                "User-Agent": user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Cookie": cookie_header,
                "Referer": "https://www.tiktok.com/creator-center/content/management",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
            }
            proxies = None
            if proxy_dict and proxy_dict.get("host") and proxy_dict.get("port"):
                proto = proxy_dict.get("protocol", "http")
                host = proxy_dict["host"]
                port = proxy_dict["port"]
                u = proxy_dict.get("username")
                p = proxy_dict.get("password")
                auth = f"{u}:{p}@" if u and p else ""
                p_url = f"{proto}://{auth}{host}:{port}"
                proxies = {"http": p_url, "https": p_url}

            resp = requests.get(
                url,
                headers=headers,
                proxies=proxies,
                impersonate="chrome120",
                timeout=timeout,
            )
            if resp.status_code == 200:
                return resp.json()
            return {"status_code": resp.status_code, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            logger.debug("TikTok Moderation API request failed for %s: %s", url, e)
            return {"status_code": -1, "error": str(e)}

    def fetch_account_standing(
        self,
        profile_id: int,
        mock_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Fetches official TikTok account standing and accumulated community strikes.
        Endpoints: https://www.tiktok.com/api/creator/account/standing/?aid=1988
        """
        conn = self._get_connection()
        try:
            row = conn.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
            if not row:
                return {"profile_id": profile_id, "ok": False, "error": "Profile not found"}

            p = dict(row)
            cookies_json = p.get("cookies_json") or p.get("cookies_browser") or ""
            cookie_hdr = parse_cookie_header_str(cookies_json)
            ua = p.get("user_agent") or "Mozilla/5.0"

            if mock_data is not None:
                data = mock_data
            else:
                if not cookie_hdr:
                    return {
                        "profile_id": profile_id,
                        "ok": False,
                        "account_standing": "Unknown",
                        "strike_count": 0,
                        "status_label": "Chưa có Cookie",
                    }
                url = "https://www.tiktok.com/api/creator/account/standing/?aid=1988"
                data = self._request_tiktok_api(url, cookie_hdr, ua)

            standing = data.get("standing_level") or "Good"
            strikes = int(data.get("active_strikes") or 0)
            restrictions = data.get("restricted_features") or []

            # Label mapping
            if standing == "Good":
                label = "🟢 Hoạt động tốt"
            elif standing == "Warning":
                label = f"🟡 Cảnh báo vi phạm ({strikes}/3 Gậy)"
            elif standing in ("High Risk", "high_risk"):
                label = f"🔴 Nguy cơ cao ({strikes}/3 Gậy)"
            elif standing in ("Suspended", "banned"):
                label = "⛔ Đã bị đình chỉ"
            else:
                label = f"Tình trạng: {standing}"

            # Persist to database
            conn.execute(
                "UPDATE profiles SET account_standing=?, strike_count=?, ttl_violations=? WHERE id=?",
                (standing, strikes, str(strikes), profile_id),
            )
            conn.commit()

            return {
                "profile_id": profile_id,
                "ok": True,
                "account_standing": standing,
                "strike_count": strikes,
                "restrictions": restrictions,
                "status_label": label,
            }
        finally:
            conn.close()

    def fetch_video_violations(
        self,
        profile_id: int,
        mock_violations: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetches penalized videos, originality strikes (ineligible for FYP/Rewards), and copyright mutes.
        Endpoint: https://www.tiktok.com/api/creator/violation/list/?aid=1988&count=20
        """
        conn = self._get_connection()
        try:
            row = conn.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
            if not row:
                return []

            p = dict(row)
            cookies_json = p.get("cookies_json") or p.get("cookies_browser") or ""
            cookie_hdr = parse_cookie_header_str(cookies_json)
            ua = p.get("user_agent") or "Mozilla/5.0"

            violations: list[dict[str, Any]] = []

            if mock_violations is not None:
                raw_list = mock_violations
            else:
                if not cookie_hdr:
                    return []
                url = "https://www.tiktok.com/api/creator/violation/list/?aid=1988&count=20"
                data = self._request_tiktok_api(url, cookie_hdr, ua)

                raw_list = data.get("violation_list") or data.get("violations")
                if raw_list is None and isinstance(data.get("data"), dict):
                    raw_list = data["data"].get("violation_list") or data["data"].get("violations")

            if not raw_list or not isinstance(raw_list, list):
                return []

            for v in raw_list:
                if not isinstance(v, dict):
                    continue
                v_id = str(v.get("item_id") or v.get("video_id") or "")
                if not v_id:
                    continue

                item = {
                    "video_id": v_id,
                    "title": str(v.get("item_title") or v.get("title") or "Video không tiêu đề"),
                    "violate_title": str(v.get("violation_title") or v.get("reason") or "Vi phạm Chính sách TikTok"),
                    "violate_description": str(
                        v.get("violation_reason") or v.get("description") or "Nội dung vi phạm."
                    ),
                    "video_posted_date": str(v.get("create_time") or ""),
                    "appeal_date": str(v.get("appeal_deadline") or ""),
                    "status": str(v.get("status") or "pending"),
                }
                violations.append(item)

                # Upsert into violateVideos
                conn.execute(
                    """
                    INSERT INTO violateVideos (
                        profile_id, video_id, title, violate_title, violate_description,
                        video_posted_date, appeal_date, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(profile_id, video_id) DO UPDATE SET
                        title=excluded.title,
                        violate_title=excluded.violate_title,
                        violate_description=excluded.violate_description,
                        appeal_date=excluded.appeal_date,
                        status=excluded.status
                    """,
                    (
                        profile_id,
                        item["video_id"],
                        item["title"],
                        item["violate_title"],
                        item["violate_description"],
                        item["video_posted_date"],
                        item["appeal_date"],
                        item["status"],
                    ),
                )
            conn.commit()
            return violations
        finally:
            conn.close()

    def get_profile_violations(self, profile_id: int) -> list[dict[str, Any]]:
        """Retrieves cached violations for a profile from database."""
        conn = self._get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM violateVideos WHERE profile_id=? ORDER BY id DESC LIMIT 100",
                (profile_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def scan_full_channel_health(self, profile_id: int) -> dict[str, Any]:
        """Runs full health check (Account Standing + Video Violations) in single pipeline."""
        standing_res = self.fetch_account_standing(profile_id)
        violations = self.fetch_video_violations(profile_id)
        return {
            "profile_id": profile_id,
            "standing": standing_res,
            "violations_count": len(violations),
            "violations": violations,
        }


__all__ = ["TikTokModerationService", "parse_cookie_header_str"]
