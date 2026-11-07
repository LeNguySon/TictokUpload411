"""
Passive TikTok Synchronization Service.
Coordinates 3-tier passive extraction:
1. Offline SQLite Cookie Extraction (SamMonny LDAP FileTime decoding).
2. Live DOM Hydration Extraction (__UNIVERSAL_DATA_FOR_REHYDRATION__ through proxy).
3. Live CDP Network Sniffing integration.
Updates SQLite profiles table and emits UI signals without requiring OAuth tokens.
"""

from __future__ import annotations

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
from src.infrastructure.tiktok.avatar_cache_service import download_and_cache_avatar
from src.infrastructure.tiktok.dom_hydration_extractor import TikTokDomHydrationExtractor
from src.infrastructure.tiktok.gologin_tiktok_client import GoLoginTikTokClient
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

    # Per-video deep analytics (2 TikTok requests each) are asked again only after this many hours.
    DEEP_VIDEO_REFRESH_HOURS = 6

    def __init__(
        self,
        profile_repo: ProfileRepository,
        proxy_repo: ProxyRepository | None = None,
        sniffer: TikTokNetworkSniffer | None = None,
        extractor: TikTokDomHydrationExtractor | None = None,
        signal_bus: AppSignalBus | None = None,
        client: GoLoginTikTokClient | None = None,
        db_path: Path | str | None = None,
    ) -> None:
        self.profile_repo = profile_repo
        self.proxy_repo = proxy_repo
        self.db_path = (
            Path(db_path)
            if db_path
            else (
                Path(profile_repo.db_path)
                if hasattr(profile_repo, "db_path") and profile_repo.db_path
                else Path("data/app.db")
            )
        )
        self.sniffer = sniffer or TikTokNetworkSniffer(db_path=self.db_path, signal_bus=signal_bus)
        self.extractor = extractor or TikTokDomHydrationExtractor()
        self.signal_bus = signal_bus or AppSignalBus.instance()
        self.client = client or GoLoginTikTokClient(db_path=self.db_path)

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
            cols = {r[1] for r in cursor.execute("PRAGMA table_info(cookies)").fetchall()}
            enc_expr = "encrypted_value" if "encrypted_value" in cols else "NULL"
            rows = cursor.execute(
                f"""
                SELECT name, value, expires_utc, {enc_expr} FROM cookies
                WHERE host_key LIKE '%tiktok.com%' OR host_key LIKE '%.tiktok.com';
                """
            ).fetchall()
            conn.close()

            encrypted_only = 0
            for name, val, expires_utc, enc_val in rows:
                if not name:
                    continue
                if not val and enc_val:
                    # Chrome/Orbita encrypt cookie values (DPAPI/AES); unreadable offline.
                    encrypted_only += 1
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

            if not is_live and encrypted_only:
                # The session cookie may well be among the encrypted ones: we cannot tell, so we do
                # not touch status or cookies (marking DIE here flagged logged-in profiles).
                logger.info(
                    "Offline cookie check for profile %s inconclusive: %d encrypted TikTok cookies",
                    profile_id,
                    encrypted_only,
                )
                return {"ok": False, "is_live": False, "cookies": cookies_found}
            if not cookies_found:
                # Fresh/empty browser profile: nothing to conclude.
                return {"ok": False, "is_live": False, "cookies": {}}

            login_state = 1 if is_live else 0
            new_status = "LIVE" if is_live else "DIE"

            # Never overwrite cookies_json: it holds the user's imported cookies (header string).
            # Browser-read cookies go to cookies_browser, in the same "name=value; ..." format.
            updates: dict[str, Any] = {"state_loggin_browser": login_state, "status": new_status}
            if is_live:
                updates["cookies_browser"] = "; ".join(f"{k}={v}" for k, v in cookies_found.items())
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
                page_html = self._fetch_page_via_proxy(row.get("id") or profile_id, url)
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

    def _fetch_page_via_proxy(self, profile_id: int | None, url: str) -> str:
        """Fetches a public page on behalf of a profile through its egress (proxy, or the user's
        explicit direct mode). Never falls back to a direct connection."""
        profile = self.profile_repo.get_by_id(profile_id) if profile_id else None
        return self._fetch_with_egress(url, profile or {"id": profile_id}, (profile or {}).get("proxy_id"))

    def _fetch_url_content(self, url: str, proxy_id: int | None) -> str:
        """Fetches URL content strictly routing through the given proxy (AgentShield Standard)."""
        return self._fetch_with_egress(url, {"id": None}, proxy_id)

    def _fetch_with_egress(self, url: str, profile: dict[str, Any], proxy_id: int | None) -> str:
        from src.infrastructure.proxy.egress import EgressBlocked, resolve_profile_egress

        proxy = self.proxy_repo.get_by_id(proxy_id) if (proxy_id and self.proxy_repo) else None
        if proxy_id and not proxy:
            logger.warning("AgentShield Strict Proxy Gate: Blocked DOM scraping for %s (invalid proxy %s)", url, proxy_id)
            return ""
        try:
            proxy_url = resolve_profile_egress(profile, proxy)
        except EgressBlocked as blocked:
            logger.warning("AgentShield Strict Proxy Gate: Blocked DOM scraping for %s (%s)", url, blocked)
            return ""
        if proxy_url and not proxy_url.startswith(("http://", "https://")):
            # urllib cannot tunnel through SOCKS: refuse rather than connect directly.
            logger.info("DOM scraping skipped for %s: SOCKS proxy not supported by this fetcher", url)
            return ""
        # Explicit (possibly empty) mapping: never pick up system proxy settings by accident.
        handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url} if proxy_url else {})
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
                body: bytes = resp.read()
                return body.decode("utf-8", errors="ignore")
        except Exception as e:
            logger.debug("Failed to fetch DOM content for %s: %s", url, e)
            return ""

    def sync_profile_deep_creator_api(self, profile_id: int) -> bool:
        """
        Executes Authenticated TikTok Creator Center APIs using GoLogin proxy and Chrome 120 TLS:
        1. /tiktokstudio/api/web/counter/getHashCount (Item counts, likes, total uploaded videos)
        2. /tiktok/creator/manage/item_list/v1/ (Recent videos, plays, views, engagement)
        3. /tiktok/v1/analytics/insights/ and /aweme/v2/data/insight/ (Views history, RPM, rewards)
        4. /mod/v1/getPenaltyDetails/ (Strikes and Community Guidelines violations)
        5. Local avatar caching
        """
        row = self.profile_repo.get_by_id(profile_id)
        if not row:
            return False

        cookie_hdr = self.client.get_profile_cookie_header(profile_id)
        if not cookie_hdr:
            return False

        clean_user = (row.get("username_on_tiktok") or row.get("name") or "").lstrip("@")
        any_success = False

        # 1. User Detail / Channel info
        try:
            url_user = f"https://www.tiktok.com/api/user/detail/?uniqueId={clean_user}"
            resp_user = self.client.request_api(profile_id, url_user, method="GET", timeout=12)
            if isinstance(resp_user, dict) and (resp_user.get("userInfo") or resp_user.get("user")):
                if self.sniffer.process_api_response(profile_id, url_user, resp_user):
                    any_success = True
        except Exception as e:
            logger.debug("Deep sync user detail error for profile %s: %s", profile_id, e)

        # 2. TikTok Studio Counter (Public videos vs Total uploaded videos, likes)
        try:
            url_counter = "https://www.tiktok.com/tiktokstudio/api/web/counter/getHashCount"
            # GET: a POST {} gets no answer at all and hung for the whole timeout on every sync (live, 2026-11).
            resp_counter = self.client.request_api(profile_id, url_counter, method="GET", timeout=10)
            if isinstance(resp_counter, dict) and ("item_count" in resp_counter or "CountData" in resp_counter):
                if self.sniffer.process_api_response(profile_id, url_counter, resp_counter):
                    any_success = True
        except Exception as e:
            logger.debug("Deep sync counter error for profile %s: %s", profile_id, e)

        # 3. TikTok Studio 2026 Item List (Videos & Views)
        try:
            url_items_2026 = "https://www.tiktok.com/tiktok/creator/manage/item_list/v1/"
            resp_items_2026 = self.client.request_api(
                profile_id,
                url_items_2026,
                method="POST",
                json_data={"cursor": 0, "size": 50, "query": {}},
                timeout=15,
            )
            if isinstance(resp_items_2026, dict) and "item_list" in resp_items_2026:
                if self.sniffer.process_api_response(profile_id, url_items_2026, resp_items_2026):
                    any_success = True
            else:
                # Fallback to legacy endpoint if available
                url_items_legacy = "https://www.tiktok.com/api/creator/item/list/?count=20"
                resp_legacy = self.client.request_api(profile_id, url_items_legacy, method="GET", timeout=12)
                if isinstance(resp_legacy, dict) and any(
                    k in resp_legacy for k in ("itemList", "items", "item_list", "creator_item_list")
                ):
                    if self.sniffer.process_api_response(profile_id, url_items_legacy, resp_legacy):
                        any_success = True
        except Exception as e:
            logger.debug("Deep sync item list error for profile %s: %s", profile_id, e)

        # 4. TikTok Studio 2026 Analytics Insights (Rewards & VV History)
        try:
            import json as _json

            type_requests = [
                {"insight_type": "INSIGHT_TYPE_ANALYTICS_OVERVIEW_REWARDS", "data_date_range": "DATA_DATE_RANGE_7D"},
                {"insight_type": "INSIGHT_TYPE_ANALYTICS_OVERVIEW_VIEWS", "data_date_range": "DATA_DATE_RANGE_7D"},
                {"insight_type": "INSIGHT_TYPE_ANALYTICS_OVERVIEW_TRAFFIC_SOURCE", "data_date_range": "DATA_DATE_RANGE_7D"},
                {"insight_type": "INSIGHT_TYPE_ANALYTICS_VIEWER_ACTIVE_HOURS", "data_date_range": "DATA_DATE_RANGE_7D"},
                {"insight_type": "INSIGHT_TYPE_ANALYTICS_VIEWER_NEW_VIEWER", "data_date_range": "DATA_DATE_RANGE_7D"},
            ]
            req_str = _json.dumps(type_requests)
            url_insights = f"https://www.tiktok.com/tiktok/v1/analytics/insights/?type_requests={req_str}&time_offset=25200&is_dark_mode=false"
            resp_insights = self.client.request_api(profile_id, url_insights, method="GET", timeout=12)
            insights_success = False
            if isinstance(resp_insights, dict) and any(
                k in resp_insights for k in ("analytics_overview_rewards", "analytics_overview_views", "analytics_overview_traffic_source")
            ):
                if self.sniffer.process_api_response(profile_id, url_insights, resp_insights):
                    any_success = True
                    insights_success = True

            # Also query aweme/v2/data/insight for retention (returning & new viewers)
            try:
                url_aweme = (
                    "https://www.tiktok.com/aweme/v2/data/insight/?aid=1988&tz_offset=25200&app_language=vi&"
                    'type_requests=[{"insigh_type":"user_rewards_data"},{"insigh_type":"vv_history","days":7,"end_days":1},{"insigh_type":"new_viewer","days":7,"end_days":1},{"insigh_type":"returning_viewer","days":7,"end_days":1}]'
                )
                resp_aweme = self.client.request_api(profile_id, url_aweme, method="GET", timeout=12)
                if isinstance(resp_aweme, dict) and any(
                    k in resp_aweme for k in ("user_rewards_data", "vv_history", "returning_viewer", "new_viewer")
                ):
                    if self.sniffer.process_api_response(profile_id, url_aweme, resp_aweme):
                        any_success = True
                        insights_success = True
            except Exception as e_aweme:
                logger.debug("Deep sync aweme insight error for profile %s: %s", profile_id, e_aweme)

            if not insights_success:
                # Fallback to legacy dashboard overview
                url_dash = "https://www.tiktok.com/api/creator/dashboard/overview/"
                resp_dash = self.client.request_api(profile_id, url_dash, method="GET", timeout=12)
                if isinstance(resp_dash, dict) and any(k in resp_dash for k in ("overview", "data", "money_earned")):
                    if self.sniffer.process_api_response(profile_id, url_dash, resp_dash):
                        any_success = True
        except Exception as e:
            logger.debug("Deep sync insights error for profile %s: %s", profile_id, e)

        # 5. TikTok Moderation & Penalty Extraction
        try:
            from src.infrastructure.tiktok.moderation_service import TikTokModerationService

            mod_svc = TikTokModerationService(db_path=self.db_path, client=self.client)
            # One penalty scan (a request per video) shared by the standing: it used to run twice per sync.
            violations = mod_svc.fetch_video_violations(profile_id)
            mod_svc.fetch_account_standing(profile_id, violations=violations)

            # Fallback legacy violation check for backward compatibility
            url_viol = "https://www.tiktok.com/api/creator/violation/"
            resp_viol = self.client.request_api(profile_id, url_viol, method="GET", timeout=12)
            if isinstance(resp_viol, dict) and any(
                k in resp_viol for k in ("violations", "violation_list", "active_strikes")
            ):
                self.sniffer.process_api_response(profile_id, url_viol, resp_viol)
        except Exception as e:
            logger.debug("Deep sync moderation check error for profile %s: %s", profile_id, e)

        # 6. Deep Audience Intelligence, Competitor Intelligence & Publish Settings
        try:
            import json as _json

            # Demographics, Active Hours, Competitor Spy
            intel = self.client.fetch_audience_intelligence(profile_id)
            prof_updates: dict[str, Any] = {}
            if intel.get("demographics"):
                prof_updates["audience_demographics_json"] = _json.dumps(intel["demographics"], ensure_ascii=False)
            from src.domain.analytics.optimal_hours import measured_optimal_schedule

            # Without activity data the parser returns a 12:00 placeholder (peak_users = 0): never store it as a
            # measurement, or every channel shows "12:00" as its best posting hour.
            opt_hours = intel.get("optimal_hours")
            measured = measured_optimal_schedule({"optimal_posting_hours_json": opt_hours}) if opt_hours else None
            if measured is not None:
                prof_updates["optimal_posting_hours_json"] = _json.dumps(opt_hours, ensure_ascii=False)
                prof_updates["optimal_hour"] = measured.hour
            if intel.get("competitor_intelligence"):
                prof_updates["competitor_intelligence_json"] = _json.dumps(intel["competitor_intelligence"], ensure_ascii=False)

            # Publish Settings (copyright & guideline auto-checks)
            pub_settings = self.client.fetch_publish_settings(profile_id)
            if pub_settings:
                prof_updates["publish_settings_json"] = _json.dumps(pub_settings, ensure_ascii=False)

            if prof_updates:
                self.profile_repo.update(profile_id, **prof_updates)
                any_success = True
        except Exception as e_intel:
            logger.debug("Deep sync audience intelligence error for profile %s: %s", profile_id, e_intel)

        # 7. Video-Level Deep Analytics (SEO Search Terms, Retention Curves, Finish Rates)
        try:
            import json as _json

            from src.infrastructure.database.connection import db_session

            # Top 5 most viewed videos not refreshed in the last DEEP_VIDEO_REFRESH_HOURS: each costs 2 TikTok
            # requests, so asking again on every sync was 10 of the 13 deep-sync calls for slowly changing data.
            with db_session(self.db_path) as conn:
                # The top 5 first, THEN skip the fresh ones (filtering first walked down to the next 5 stale videos).
                v_rows = conn.execute(
                    """
                    SELECT top.video_id FROM (
                        SELECT video_id FROM videoTables WHERE profile_id = ? AND video_id IS NOT NULL
                        ORDER BY views DESC, id DESC LIMIT 5
                    ) AS top
                    LEFT JOIN video_deep_analytics d ON d.aweme_id = top.video_id
                    WHERE d.updated_at IS NULL OR d.updated_at < datetime('now', ?);
                    """,
                    (profile_id, f"-{self.DEEP_VIDEO_REFRESH_HOURS} hours"),
                ).fetchall()
                v_ids = [r["video_id"] for r in v_rows if r["video_id"]]

            for vid in v_ids:
                try:
                    v_analytics = self.client.fetch_video_deep_analytics(profile_id, vid)
                    if not (v_analytics.get("search_terms") or (v_analytics.get("retention") or {}).get("points")):
                        # TikTok has nothing for this video yet: remember the attempt (refresh window) only.
                        with db_session(self.db_path) as conn:
                            conn.execute(
                                """
                                INSERT INTO video_deep_analytics (aweme_id, profile_id, updated_at)
                                VALUES (?, ?, CURRENT_TIMESTAMP)
                                ON CONFLICT(aweme_id) DO UPDATE SET updated_at = CURRENT_TIMESTAMP;
                                """,
                                (vid, profile_id),
                            )
                    if v_analytics and (v_analytics.get("search_terms") or v_analytics.get("retention", {}).get("points")):
                        st_json = _json.dumps(v_analytics.get("search_terms") or [], ensure_ascii=False)
                        ts_json = _json.dumps(v_analytics.get("traffic_sources") or {}, ensure_ascii=False)
                        ret_data = v_analytics.get("retention") or {}
                        ret_pts_json = _json.dumps(ret_data.get("points") or [], ensure_ascii=False)
                        fn_rate = float(ret_data.get("finish_rate") or 0.0)
                        ai_json = _json.dumps(v_analytics.get("ai_comments") or {}, ensure_ascii=False)

                        with db_session(self.db_path) as conn:
                            conn.execute(
                                """
                                UPDATE videoTables SET
                                    search_terms_json = ?,
                                    traffic_sources_json = ?,
                                    retention_points_json = ?,
                                    finish_rate = ?,
                                    ai_comments_json = ?
                                WHERE profile_id = ? AND video_id = ?;
                                """,
                                (st_json, ts_json, ret_pts_json, fn_rate, ai_json, profile_id, vid)
                            )
                            conn.execute(
                                """
                                INSERT INTO video_deep_analytics (
                                    aweme_id, profile_id, search_terms_json, traffic_sources_json,
                                    retention_points_json, finish_rate, ai_comments_json, updated_at
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                                ON CONFLICT(aweme_id) DO UPDATE SET
                                    search_terms_json = excluded.search_terms_json,
                                    traffic_sources_json = excluded.traffic_sources_json,
                                    retention_points_json = excluded.retention_points_json,
                                    finish_rate = excluded.finish_rate,
                                    ai_comments_json = excluded.ai_comments_json,
                                    updated_at = CURRENT_TIMESTAMP;
                                """,
                                (vid, profile_id, st_json, ts_json, ret_pts_json, fn_rate, ai_json)
                            )
                except Exception as e_v:
                    logger.debug("Failed video deep analytics sync for %s: %s", vid, e_v)
        except Exception as e_vids:
            logger.debug("Deep sync video list analytics error for profile %s: %s", profile_id, e_vids)

        # 8. Local Avatar Caching
        try:
            updated_row = self.profile_repo.get_by_id(profile_id)
            if updated_row and updated_row.get("avatar_url"):
                download_and_cache_avatar(
                    profile_id=profile_id,
                    avatar_url=updated_row["avatar_url"],
                    storage_dir=updated_row.get("storage_dir"),
                    db_path=self.db_path,
                )
        except Exception as ae:
            logger.debug("Avatar caching error for profile %s: %s", profile_id, ae)

        return any_success

    def sync_single_profile(self, profile_id: int) -> dict[str, Any]:
        """
        Orchestrates complete 4-tier telemetry synchronization for a single profile:
        1. Checks offline SQLite cookies for LIVE/DIE and session validity.
        2. If cookie is present, performs Deep Authenticated Creator API Sync via GoLogin proxy.
        3. If no cookie or Deep Sync is not available, falls back to public DOM Hydration.
        4. Updates statistic_date_update and emits profile_updated to GUI.
        """
        # 1. Offline Cookie Check
        cookie_res = self.sync_profile_offline_cookies(profile_id)

        # 2. Deep Creator Center Authenticated Sync
        deep_res = False
        try:
            deep_res = self.sync_profile_deep_creator_api(profile_id)
        except Exception as de:
            logger.debug("Deep creator API check error on profile %s: %s", profile_id, de)

        # 3. Public DOM Hydration Fallback (if Deep Sync didn't run or failed)
        dom_res = None
        if not deep_res:
            try:
                dom_res = self.sync_profile_dom_hydration(profile_id)
            except Exception as dme:
                logger.debug("DOM hydration check error on profile %s: %s", profile_id, dme)

        # 4. Record sync attempt timestamp in database
        now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        self.profile_repo.update(profile_id, statistic_date_update=now_str)

        # 5. Pull latest row from DB to compile complete update payload
        row = self.profile_repo.get_by_id(profile_id) or {}

        # 6. Emit signal to GUI
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
            "views_month": row.get("views_month", 0),
            "total_views": row.get("total_views", 0),
            "cookies_count": len(cookie_res.get("cookies", {})),
            "dom_synced": bool(dom_res),
            "deep_synced": bool(deep_res),
        }
