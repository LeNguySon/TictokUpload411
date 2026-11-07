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
from typing import Any, cast

from src.infrastructure.credentials.dpapi import unprotect_text
from src.infrastructure.database.connection import get_db_connection

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
            except Exception as ignored:
                logger.debug("parse_cookies_to_header: ignored error: %s", ignored)
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
        # Configured connection (busy_timeout 10 s, WAL, foreign keys): a bare sqlite3.connect
        # waited only 5 s and failed with "database is locked" while uploads were writing.
        return get_db_connection(self.db_path)

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
                except Exception as ignored:
                    logger.debug("get_profile_cookie_header: ignored error: %s", ignored)
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
        from src.infrastructure.proxy.egress import build_proxy_url

        return build_proxy_url(proxy_dict)  # encoded credentials, socks5h (remote DNS)

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
        from curl_cffi.requests import HttpMethod, ProxySpec

        conn = self._get_connection()
        try:
            row = conn.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
            if not row:
                return {"status_code": -1, "error": "Profile not found"}
            p = dict(row)
        finally:
            conn.close()

        cookie_hdr = self.get_profile_cookie_header(profile_id)
        from src.infrastructure.proxy.egress import resolve_profile_egress

        # Raises EgressBlocked (a PermissionError) for no proxy, a leak-flagged or a broken proxy;
        # None only for the user's explicit direct mode.
        proxy_url = resolve_profile_egress(p, self.get_profile_proxy(profile_id))
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
                cast("HttpMethod", method.upper()),
                url,
                headers=req_headers,
                json=json_data,
                data=data,
                proxies=cast("ProxySpec | None", proxies),
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

        raw_data = res.get("data")
        data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
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

    def fetch_audience_intelligence(self, profile_id: int) -> dict[str, Any]:
        """Fetches demographics (countries, cities, age, gender), optimal posting hours,
        and peer competitor intelligence via /tiktok/v1/analytics/insights/ and /aweme/v2/data/insight/.
        """
        import json as _json

        from src.infrastructure.tiktok.deep_analytics_parser import (
            calculate_optimal_post_hours,
            parse_audience_demographics,
            parse_competitor_intelligence,
        )

        # 1. Demographics batch
        demo_requests = [
            {"insight_type": "INSIGHT_TYPE_ANALYTICS_FOLLOWER_COUNTRY_CITY_PERCENT", "data_date_range": "DATA_DATE_RANGE_7D"},
            {"insight_type": "INSIGHT_TYPE_ANALYTICS_FOLLOWER_GENDER_PERCENT", "data_date_range": "DATA_DATE_RANGE_7D"},
            {"insight_type": "INSIGHT_TYPE_ANALYTICS_FOLLOWER_AGE_PERCENT", "data_date_range": "DATA_DATE_RANGE_7D"},
            {"insight_type": "INSIGHT_TYPE_ANALYTICS_VIEWER_TOTAL_VIEWER", "data_date_range": "DATA_DATE_RANGE_7D"},
        ]
        url_demo = f"https://www.tiktok.com/tiktok/v1/analytics/insights/?type_requests={_json.dumps(demo_requests)}&time_offset=25200&is_dark_mode=false"
        res_demo = self.request_api(profile_id, url_demo, method="GET", timeout=15)
        demographics = parse_audience_demographics(res_demo)

        # 2. Follower Active Hours & Peer Competitors batch
        aweme_requests = [
            {"insigh_type": "follower_active_history_hours", "days": 8, "end_days": 1},
            {"insigh_type": "follower_active_history_days", "days": 8, "end_days": 1},
            {"insigh_type": "top10_other_creators_recommendation"},
            {"insigh_type": "top10_other_videos_recommendation"},
        ]
        url_aweme = f"https://www.tiktok.com/aweme/v2/data/insight/?aid=1988&tz_offset=25200&app_language=en&type_requests={_json.dumps(aweme_requests)}"
        res_aweme = self.request_api(profile_id, url_aweme, method="GET", timeout=15)

        raw_hours = res_aweme.get("follower_active_history_hours")
        optimal_hours = calculate_optimal_post_hours(raw_hours if isinstance(raw_hours, list) else [])

        raw_users = res_aweme.get("viewer_also_watched_users") or res_aweme.get("top10_other_creators_recommendation")
        raw_items = res_aweme.get("viewer_also_watched_items") or res_aweme.get("top10_other_videos_recommendation")
        competitor_intel = parse_competitor_intelligence(raw_users, raw_items)

        return {
            "demographics": demographics,
            "optimal_hours": optimal_hours,
            "competitor_intelligence": competitor_intel,
        }

    def fetch_video_deep_analytics(self, profile_id: int, aweme_id: str | int) -> dict[str, Any]:
        """Fetches search terms (SEO), retention curve, finish rate, and traffic sources for a video."""
        import json as _json

        from src.infrastructure.tiktok.deep_analytics_parser import (
            parse_retention_data,
            parse_search_terms,
            parse_traffic_source_matrix,
        )

        item_str = str(aweme_id)
        video_requests = [
            {"insigh_type": "video_info", "aweme_id": item_str},
            {"insigh_type": "item_search_terms", "aweme_id": item_str},
            {"insigh_type": "video_traffic_source_percent_realtime", "aweme_id": item_str},
            {"insigh_type": "video_retention_rate_realtime", "aweme_id": item_str},
            {"insigh_type": "video_finish_rate_realtime", "aweme_id": item_str},
        ]
        url = f"https://www.tiktok.com/aweme/v2/data/insight/?aid=1988&tz_offset=25200&app_language=en&type_requests={_json.dumps(video_requests)}"
        res = self.request_api(profile_id, url, method="GET", timeout=15)

        search_terms = parse_search_terms(res.get("item_search_terms"))
        traffic_matrix = parse_traffic_source_matrix(res.get("video_traffic_source_percent_realtime"))
        retention = parse_retention_data(res.get("video_retention_rate_realtime"), res.get("video_finish_rate_realtime"))

        # AI Comment Overview
        ai_comments = self.fetch_ai_comment_overview(profile_id, item_str)

        return {
            "aweme_id": item_str,
            "search_terms": search_terms,
            "traffic_sources": traffic_matrix,
            "retention": retention,
            "ai_comments": ai_comments,
        }

    def fetch_publish_settings(self, profile_id: int) -> dict[str, Any]:
        """Queries /tiktok/v1/creator/publish_setting/ to verify automated copyright and content check toggles."""
        url = "https://www.tiktok.com/tiktok/v1/creator/publish_setting/?aid=1988&app_name=tiktok_web"
        res = self.request_api(profile_id, url, method="GET", timeout=10)
        keys = ("enable_auto_music_copyright_check", "enable_auto_post_check", "disable_tto_plus_showcase")
        failed = (
            "error" in res
            or res.get("_status_code", 200) != 200
            or res.get("status_code") not in (None, 0)  # TikTok API error inside an HTTP 200
            or not any(k in res for k in keys)
        )
        if failed:
            # Unknown, not "checks OFF": the caller stores nothing instead of a false "copyright check disabled".
            logger.debug("Publish settings unavailable for profile %s: %s", profile_id, res.get("status_msg") or res.get("error"))
            return {}
        return {
            "enable_auto_music_copyright_check": bool(res.get("enable_auto_music_copyright_check")),
            "enable_auto_post_check": bool(res.get("enable_auto_post_check")),
            "disable_tto_plus_showcase": bool(res.get("disable_tto_plus_showcase")),
            "status_code": res.get("_status_code", 200),
        }

    def fetch_ai_comment_overview(self, profile_id: int, item_id: str | int) -> dict[str, Any]:
        """Queries /tiktok/v1/creator/ai_comment/analytics_overview for comment categorizations & topics."""
        from src.infrastructure.tiktok.deep_analytics_parser import parse_ai_comments

        item_str = str(item_id)
        url = "https://www.tiktok.com/tiktok/v1/creator/ai_comment/analytics_overview?aid=1988&app_name=tiktok_web"
        payload = {"item_id": int(item_str) if item_str.isdigit() else item_str, "item_id_str": item_str}
        res = self.request_api(profile_id, url, method="POST", json_data=payload, timeout=12)
        return parse_ai_comments(res)
