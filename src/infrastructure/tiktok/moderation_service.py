"""
TikTok Moderation Service.
Interacts with official TikTok Creator Center Moderation Endpoints:
- Account standing & community guideline strikes (/api/creator/account/standing/)
- Video guideline violations, originality strikes, and sound copyright (/api/creator/violation/list/)
- Video Violation Appeals (/creator-center/api/violation/appeal)
- Creator Rewards Program Re-application (/creator-center/api/creator/rewards/reapply)
Learned from Gloglin2609/engine/tiktok/moderation_service.py and monetization_service.py.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from src.domain.licensing import entitlements
from src.domain.licensing.plans import Feature
from src.domain.policies.cookie_source import pick_session_cookie
from src.infrastructure.database.connection import get_db_connection
from src.infrastructure.tiktok.gologin_tiktok_client import (
    GoLoginTikTokClient,
    parse_cookies_to_header,
)
from src.infrastructure.tiktok.network_sniffer import hash_count_data

logger = logging.getLogger(__name__)

# getPenaltyDetails requests in flight at once during a violation scan (one per video; no flag in item_list).
PENALTY_LOOKUP_WORKERS = 8
# Safety cap on item_list/v1 pagination.
ITEM_LIST_MAX_ITEMS = 2000


PAGE_TYPE_MAP: dict[int, str] = {
    1: "PenaltyDetailPage",
    2: "AppealRejectedPage",
    3: "AppealReceivedPage",
    4: "AppealExpiredPage",
    5: "AppealApprovedPage",
    6: "AppealSubmittedPage",
}


def parse_cookie_header_str(cookies_data: Any) -> str:
    """Parses various cookie representations into a valid HTTP Cookie header string."""
    return parse_cookies_to_header(cookies_data)


class TikTokModerationService:
    """Service for querying and persisting TikTok channel health, strikes, video violations, and appeals."""

    def __init__(
        self,
        db_path: Path | str | None = None,
        client: GoLoginTikTokClient | None = None,
    ) -> None:
        self.db_path = Path(db_path or "data/app.db")
        self.client = client or GoLoginTikTokClient(db_path=self.db_path)

    def _get_connection(self) -> sqlite3.Connection:
        # Configured connection (busy_timeout 10 s, WAL, foreign keys): a bare sqlite3.connect
        # waited only 5 s and failed with "database is locked" while uploads were writing.
        return get_db_connection(self.db_path)

    def _request_tiktok_api(
        self,
        url: str,
        cookie_header: str,
        user_agent: str,
        proxy_dict: dict[str, Any] | None = None,
        timeout: int = 15,
        profile_id: int | None = None,
        method: str = "GET",
        json_data: Any = None,
    ) -> dict[str, Any]:
        """Executes HTTP request routed through GoLogin TikTok client or fallback."""
        if profile_id is not None:
            return self.client.request_api(
                profile_id, url, method=method, json_data=json_data, timeout=timeout
            )

        try:
            from curl_cffi import requests
            from curl_cffi.requests import HttpMethod, ProxySpec

            headers = {
                "User-Agent": user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Cookie": cookie_header,
                "Referer": "https://www.tiktok.com/creator-center/content/management",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
            }
            from src.infrastructure.proxy.egress import EgressBlocked, resolve_profile_egress

            try:
                # No profile here, so no direct opt-in: a proxy is mandatory (it used to go direct).
                p_url = resolve_profile_egress({"id": None}, proxy_dict)
            except EgressBlocked as blocked:
                logger.warning("TikTok moderation request refused: %s", blocked)
                return {"status_code": -1, "error": str(blocked)}
            proxies = {"http": p_url, "https": p_url} if p_url else None

            resp = requests.request(
                cast("HttpMethod", method.upper()),
                url,
                headers=headers,
                json=json_data,
                proxies=cast("ProxySpec | None", proxies),
                impersonate="chrome120",
                timeout=timeout,
            )
            if resp.status_code == 200:
                payload: dict[str, Any] = resp.json()
                return payload
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
        Fetches official TikTok Studio 2026 account standing, active strikes, and video count ratio.
        Endpoints:
        - GET https://www.tiktok.com/tiktokstudio/api/web/counter/getHashCount
        - POST https://www.tiktok.com/tiktok/creator/manage/item_list/v1/
        """
        entitlements.require(Feature.CHANNEL_HEALTH)  # Gói 3
        conn = self._get_connection()
        try:
            row = conn.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
            if not row:
                return {"profile_id": profile_id, "ok": False, "error": "Profile not found"}

            p = dict(row)
            cookies_json = pick_session_cookie(p)  # refreshed browser session first
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
                        "public_items": 0,
                        "total_items": 0,
                        "removed_items": 0,
                        "status_label": "Chưa có Cookie",
                    }
                # Query 2026 TikTok Studio Counter via _request_tiktok_api wrapper
                url_counter = "https://www.tiktok.com/tiktokstudio/api/web/counter/getHashCount"
                # GET (a POST {} gets no answer: 10 s timeout); counters are under CountData.<uid>.
                data = hash_count_data(
                    self._request_tiktok_api(url_counter, cookie_hdr, ua, profile_id=profile_id, method="GET")
                )

            # Check if direct/legacy standing mock was supplied
            if "standing_level" in data or "active_strikes" in data:
                standing = data.get("standing_level") or "Good"
                strikes = int(data.get("active_strikes") or 0)
                item_count = int(data.get("item_count") or p.get("total_videos") or 0)
                total_item_count = int(data.get("total_item_count") or item_count)
                restrictions = data.get("restricted_features") or []
            else:
                item_count = int(data.get("item_count") or p.get("total_videos") or 0)
                total_item_count = int(data.get("total_item_count") or item_count)
                violations = self.fetch_video_violations(profile_id)
                strikes = len(violations)
                restrictions = []

                if strikes == 0:
                    standing = "Good"
                elif strikes == 1:
                    standing = "Warning"
                else:
                    standing = "High Risk"

            removed_items = max(0, total_item_count - item_count)

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
                "UPDATE profiles SET account_standing=?, strike_count=?, ttl_violations=?, total_videos=? WHERE id=?",
                (standing, strikes, str(strikes), item_count, profile_id),
            )
            conn.commit()

            return {
                "profile_id": profile_id,
                "ok": True,
                "account_standing": standing,
                "strike_count": strikes,
                "public_items": item_count,
                "total_items": total_item_count,
                "removed_items": removed_items,
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
        Fetches penalized videos, originality strikes (ineligible for FYP/Rewards), and policy sanctions.
        Endpoints:
        - POST https://www.tiktok.com/tiktok/creator/manage/item_list/v1/
        - GET https://www.tiktok.com/mod/v1/getPenaltyDetails/?vid=<item_id>
        """
        entitlements.require(Feature.CHANNEL_HEALTH)  # Gói 3
        conn = self._get_connection()
        try:
            row = conn.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
            if not row:
                return []

            p = dict(row)
            cookies_json = pick_session_cookie(p)  # refreshed browser session first
            cookie_hdr = parse_cookie_header_str(cookies_json)
            ua = p.get("user_agent") or "Mozilla/5.0"

            violations: list[dict[str, Any]] = []

            if mock_violations is not None:
                raw_list = mock_violations
                for raw in raw_list:
                    item_id = str(raw.get("item_id") or raw.get("video_id") or "")
                    if not item_id:
                        continue
                    title = raw.get("item_title") or raw.get("title") or "Video TikTok"
                    v_title = raw.get("violation_title") or raw.get("reason_title") or "Gậy Vi Phạm Chính Sách"
                    v_desc = raw.get("violation_reason") or raw.get("reason") or "Không tuân thủ nguyên tắc cộng đồng"
                    deadline = raw.get("appeal_deadline") or raw.get("appeal_date") or ""
                    status_v = raw.get("status") or "pending"
                    violations.append({
                        "video_id": item_id,
                        "title": title,
                        "violate_title": v_title,
                        "violate_description": v_desc,
                        "video_posted_date": raw.get("create_time", ""),
                        "appeal_date": deadline,
                        "status": status_v,
                    })
            else:
                if not cookie_hdr:
                    return []

                # Query authentic 2026 TikTok Studio Item List
                url_items = "https://www.tiktok.com/tiktok/creator/manage/item_list/v1/"
                resp_items = self._request_tiktok_api(
                    url_items,
                    cookie_hdr,
                    ua,
                    profile_id=profile_id,
                    method="POST",
                    json_data={"cursor": 0, "size": 50, "query": {}},
                    timeout=15,
                )

                # Check if legacy violation_list was returned by mock
                legacy_list = resp_items.get("violation_list") or resp_items.get("violations")
                if legacy_list and isinstance(legacy_list, list):
                    for raw in legacy_list:
                        item_id = str(raw.get("item_id") or raw.get("video_id") or "")
                        if not item_id:
                            continue
                        title = raw.get("item_title") or raw.get("title") or "Video TikTok"
                        v_title = raw.get("violation_title") or raw.get("reason_title") or "Gậy Vi Phạm Chính Sách"
                        v_desc = raw.get("violation_reason") or raw.get("reason") or "Không tuân thủ nguyên tắc cộng đồng"
                        deadline = raw.get("appeal_deadline") or raw.get("appeal_date") or ""
                        status_v = raw.get("status") or "pending"
                        violations.append({
                            "video_id": item_id,
                            "title": title,
                            "violate_title": v_title,
                            "violate_description": v_desc,
                            "video_posted_date": raw.get("create_time", ""),
                            "appeal_date": deadline,
                            "status": status_v,
                        })
                else:
                    items = self._list_all_items(resp_items, cookie_hdr, ua, profile_id)
                    violations.extend(self._penalized_items(items, cookie_hdr, ua, profile_id))

            for item in violations:
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

    def _list_all_items(
        self, first_page: dict[str, Any], cookie_hdr: str, ua: str, profile_id: int
    ) -> list[dict[str, Any]]:
        """Every video of the channel: follows item_list/v1 pagination (``has_more`` / ``cursor``)."""
        items: list[dict[str, Any]] = [it for it in (first_page.get("item_list") or []) if isinstance(it, dict)]
        page = first_page
        seen_cursors: set[Any] = set()
        while page.get("has_more") and len(items) < ITEM_LIST_MAX_ITEMS:
            cursor = page.get("cursor")
            if cursor in (None, "") or cursor in seen_cursors:
                break  # no usable cursor: stop rather than loop on the same page
            seen_cursors.add(cursor)
            page = self._request_tiktok_api(
                "https://www.tiktok.com/tiktok/creator/manage/item_list/v1/",
                cookie_hdr,
                ua,
                profile_id=profile_id,
                method="POST",
                json_data={"cursor": cursor, "size": 50, "query": {}},
                timeout=15,
            )
            batch = [it for it in (page.get("item_list") or []) if isinstance(it, dict)]
            if not batch:
                break
            items.extend(batch)
        return items

    def _penalized_items(
        self, items: list[dict[str, Any]], cookie_hdr: str, ua: str, profile_id: int
    ) -> list[dict[str, Any]]:
        """getPenaltyDetails for every video, PENALTY_LOOKUP_WORKERS at a time; keeps the item order.

        item_list/v1 carries no penalty flag (a penalized video looks like any other), so each video is
        checked; doing it sequentially took ~85 s for 79 videos.
        """
        from concurrent.futures import ThreadPoolExecutor

        candidates = [it for it in items if str(it.get("item_id") or it.get("id") or "")]

        def lookup(it: dict[str, Any]) -> dict[str, Any] | None:
            item_id = str(it.get("item_id") or it.get("id") or "")
            url_pen = f"https://www.tiktok.com/mod/v1/getPenaltyDetails/?vid={item_id}"
            resp_pen = self._request_tiktok_api(url_pen, cookie_hdr, ua, profile_id=profile_id, method="GET", timeout=8)
            penalties = resp_pen.get("penalties") or []
            appeal_st = resp_pen.get("appeal_status")
            if not (penalties or (appeal_st is not None and appeal_st != 2)):
                return None

            title = str(it.get("desc") or it.get("item_title") or it.get("title") or "#shorts")
            v_title = "Community Guidelines"
            v_desc = "Ineligible for the For You feed (FYF)"
            appeal_deadline = ""
            if penalties:
                p0 = penalties[0]
                reasons = p0.get("penalty_reason_info_list") or []
                if reasons and isinstance(reasons[0], dict):
                    v_title = reasons[0].get("title") or v_title
                    v_desc = reasons[0].get("content") or v_desc
                appeal_deadline = str(p0.get("date") or "")

            status_str = "can_appeal" if appeal_st == 0 else ("under_review" if appeal_st == 1 else "penalized")
            return {
                "video_id": item_id,
                "title": title,
                "violate_title": v_title,
                "violate_description": v_desc,
                "video_posted_date": str(it.get("create_time") or ""),
                "appeal_date": appeal_deadline,
                "status": status_str,
            }

        if not candidates:
            return []
        with ThreadPoolExecutor(max_workers=min(PENALTY_LOOKUP_WORKERS, len(candidates))) as pool:
            results = list(pool.map(lookup, candidates))
        return [r for r in results if r is not None]

    def fetch_video_appeal_info(self, profile_id: int, video_id: str) -> dict[str, Any]:
        """
        Queries authentic TikTok Studio 2026 transparency & penalty moderation page content.
        Endpoint: GET https://www.tiktok.com/api/moderation/penalties/gettransparencypagecontent?entityId=<item_id>
        """
        entitlements.require(Feature.CHANNEL_HEALTH)
        url = f"https://www.tiktok.com/api/moderation/penalties/gettransparencypagecontent?entityId={video_id}"
        resp = self.client.request_api(profile_id, url, method="GET", timeout=12)

        page_type = int(resp.get("transparencyModerationPageType") or 0)
        show_appeal = bool(resp.get("showAppealBtn", False))
        appeal_details = resp.get("appealDetails") or []
        penalties = resp.get("penalties") or []
        btn_desc = str(resp.get("appealBtnDescription") or "Appeal")
        is_eea = bool(resp.get("isUserEEA", False))

        return {
            "video_id": str(video_id),
            "show_appeal_btn": show_appeal,
            "appeal_details": appeal_details,
            "penalties": penalties,
            "page_type": page_type,
            "page_type_name": PAGE_TYPE_MAP.get(page_type, f"UnknownPage_{page_type}"),
            "appeal_btn_desc": btn_desc,
            "is_user_eea": is_eea,
            "raw": resp,
        }

    def submit_video_appeal(
        self,
        profile_id: int,
        video_id: str,
        appeal_reason: str,
        *,
        mock_success: bool = False,
        penalty_id: str | None = None,
        penalty_source: int = 1,
    ) -> dict[str, Any]:
        """
        Submits an official appeal for a penalized video using TikTok Studio 2026 endpoints:
        - Primary: POST https://www.tiktok.com/api/moderation/penalties/submitappeal (SubmitAppealsV2)
        - Fallback: POST https://www.tiktok.com/mod/v1/submitAppeals (ModV1)
        Updates violateVideos status to 'appealed' and logs a new ticket in accountAppeals.
        """
        entitlements.require(Feature.CHANNEL_HEALTH)  # Gói 3
        conn = self._get_connection()
        try:
            row = conn.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
            if not row:
                return {"ok": False, "error": "Profile not found"}

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            endpoint_used = "mock"

            if not mock_success:
                # 1. Fetch live transparency and appealDetails if not explicitly provided
                appeal_details: list[dict[str, Any]] = []
                if penalty_id:
                    appeal_details = [{"penaltyID": str(penalty_id), "penaltySource": penalty_source}]
                else:
                    info = self.fetch_video_appeal_info(profile_id, video_id)
                    if not info.get("show_appeal_btn"):
                        return {
                            "ok": False,
                            "error": f"Video không đủ điều kiện hoặc đã hết hạn kháng cáo (Trạng thái: {info.get('page_type_name')}).",
                            "page_type": info.get("page_type"),
                            "page_type_name": info.get("page_type_name"),
                        }
                    appeal_details = info.get("appeal_details") or []
                    if not appeal_details and info.get("penalties"):
                        p0 = info["penalties"][0]
                        pid = p0.get("penalty_id", {}).get("id") or p0.get("id")
                        if pid:
                            appeal_details = [{"penaltyID": str(pid), "penaltySource": penalty_source}]

                # 2. Try Primary Endpoint: SubmitAppealsV2 (/api/moderation/penalties/submitappeal)
                url_v2 = "https://www.tiktok.com/api/moderation/penalties/submitappeal"
                payload_v2 = {
                    "appealDetails": appeal_details,
                    "itemId": str(video_id),
                }
                api_res = self.client.request_api(profile_id, url_v2, method="POST", json_data=payload_v2)

                v2_success = False
                base_resp = api_res.get("BaseResp") or {}
                if base_resp.get("StatusCode") == 0 or api_res.get("status_code") == 0:
                    v2_success = True
                    endpoint_used = "V2_submitappeal"
                elif api_res.get("_status_code") in (200, 201) and not base_resp.get("StatusCode"):
                    v2_success = True
                    endpoint_used = "V2_submitappeal"

                # 3. Fallback: Try ModV1 SubmitAppeals (/mod/v1/submitAppeals)
                if not v2_success:
                    logger.info("V2 appeal endpoint failed or returned non-zero, falling back to ModV1...")
                    url_v1 = "https://www.tiktok.com/mod/v1/submitAppeals"
                    mod_p_id = appeal_details[0]["penaltyID"] if appeal_details else str(video_id)
                    mod_details = [{"issuer": "TNS", "penalty_id": str(mod_p_id)}]
                    payload_v1 = {
                        "vid": str(video_id),
                        "appeal_details": json.dumps(mod_details),
                    }
                    api_res_v1 = self.client.request_api(profile_id, url_v1, method="POST", json_data=payload_v1)
                    if api_res_v1.get("status_code") == 0 or api_res_v1.get("_status_code") in (200, 201):
                        endpoint_used = "ModV1_submitAppeals"
                    else:
                        err = (
                            api_res_v1.get("status_msg")
                            or api_res.get("BaseResp", {}).get("StatusMessage")
                            or "appeal_rejected_by_api"
                        )
                        logger.warning("TikTok appeal API returned error: %s", err)
                        return {"ok": False, "error": f"TikTok API từ chối: {err}"}

            # 1. Update violateVideos
            conn.execute(
                """
                INSERT INTO violateVideos (profile_id, video_id, status, appeal_date)
                VALUES (?, ?, 'appealed', ?)
                ON CONFLICT(profile_id, video_id) DO UPDATE SET
                    status='appealed',
                    appeal_date=excluded.appeal_date
                """,
                (profile_id, str(video_id), now_str),
            )

            # 2. Insert into accountAppeals
            conn.execute(
                """
                INSERT INTO accountAppeals (
                    profile_id, appeal_type, object_id, reason, status, submitted_at, updated_at
                ) VALUES (?, 'video_strike', ?, ?, 'submitted', ?, ?)
                """,
                (profile_id, str(video_id), appeal_reason, now_str, now_str),
            )

            # 3. Update profile appealViolateDate
            conn.execute("UPDATE profiles SET appealViolateDate=? WHERE id=?", (now_str, profile_id))
            conn.commit()

            return {
                "ok": True,
                "profile_id": profile_id,
                "video_id": str(video_id),
                "status": "appealed",
                "appeal_date": now_str,
                "endpoint_used": endpoint_used,
                "message": f"Đã nộp đơn kháng nghị cho video #{video_id}.",
            }
        finally:
            conn.close()

    def submit_creator_rewards_reapply(
        self,
        profile_id: int,
        *,
        mock_success: bool = False,
    ) -> dict[str, Any]:
        """
        Submits re-application to TikTok Creator Rewards Program after penalty period.
        Verifies that date_reapply countdown has reached 0 before allowing re-submission.
        Endpoint: https://www.tiktok.com/creator-center/api/creator/rewards/reapply
        """
        entitlements.require(Feature.CHANNEL_HEALTH)  # Gói 3
        conn = self._get_connection()
        try:
            row = conn.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
            if not row:
                return {"ok": False, "error": "Profile not found"}

            p = dict(row)
            date_reapply = p.get("date_reapply")

            if date_reapply:
                try:
                    target_dt = datetime.fromisoformat(str(date_reapply))
                    now_dt = datetime.now()
                    if target_dt.tzinfo is not None and now_dt.tzinfo is None:
                        now_dt = now_dt.astimezone()
                    elif target_dt.tzinfo is None and now_dt.tzinfo is not None:
                        target_dt = target_dt.astimezone()

                    seconds = (target_dt - now_dt).total_seconds()
                    if seconds > 0:
                        days_left = max(1, math.ceil(seconds / 86400))
                        return {
                            "ok": False,
                            "days_left": days_left,
                            "date_reapply": str(date_reapply),
                            "error": f"Thời gian nộp lại đơn chưa đến hạn (còn {days_left} ngày).",
                        }
                except Exception as ignored:
                    logger.debug("submit_creator_rewards_reapply: ignored error: %s", ignored)

            if not mock_success:
                url = "https://www.tiktok.com/creator-center/api/creator/rewards/reapply"
                self.client.request_api(profile_id, url, method="POST", json_data={})

            # Update profile standing to Good and clear date_reapply
            conn.execute(
                "UPDATE profiles SET account_standing='Good', date_reapply=NULL WHERE id=?",
                (profile_id,),
            )
            conn.commit()

            return {
                "ok": True,
                "profile_id": profile_id,
                "status": "submitted",
                "message": "Đã nộp lại đơn gia nhập Quỹ Nhà Sáng Tạo thành công.",
            }
        finally:
            conn.close()

    def check_appeal_status(self, profile_id: int) -> dict[str, Any]:
        """
        Checks status of pending appeals via authentic TikTok Studio transparency API.
        Reconciles violateVideos & accountAppeals automatically based on transparencyModerationPageType:
        - 1: PenaltyDetailPage (Penalized / Can appeal)
        - 2: AppealRejectedPage (Rejected)
        - 3/6: AppealReceivedPage / AppealSubmittedPage (Under review)
        - 4: AppealExpiredPage (Expired)
        - 5: AppealApprovedPage (Approved / Gậy đã gỡ!)
        """
        entitlements.require(Feature.CHANNEL_HEALTH)  # Gói 3
        conn = self._get_connection()
        try:
            # Query active appealed items
            pending_violations = conn.execute(
                "SELECT * FROM violateVideos WHERE profile_id=? AND status IN ('appealed', 'under_review', 'pending')",
                (profile_id,),
            ).fetchall()

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            resolved_count = 0
            rejected_count = 0
            reviewing_count = 0

            for v in pending_violations:
                v_dict = dict(v)
                vid = v_dict.get("video_id")
                if not vid:
                    continue

                try:
                    info = self.fetch_video_appeal_info(profile_id, vid)
                    pt = info.get("page_type")
                    if pt == 5:  # AppealApprovedPage
                        conn.execute(
                            "UPDATE violateVideos SET status='resolved', appeal_date=? WHERE profile_id=? AND video_id=?",
                            (now_str, profile_id, vid),
                        )
                        conn.execute(
                            "UPDATE accountAppeals SET status='approved', updated_at=? WHERE profile_id=? AND object_id=?",
                            (now_str, profile_id, vid),
                        )
                        resolved_count += 1
                    elif pt == 2:  # AppealRejectedPage
                        conn.execute(
                            "UPDATE violateVideos SET status='penalized', appeal_date=? WHERE profile_id=? AND video_id=?",
                            (now_str, profile_id, vid),
                        )
                        conn.execute(
                            "UPDATE accountAppeals SET status='rejected', updated_at=? WHERE profile_id=? AND object_id=?",
                            (now_str, profile_id, vid),
                        )
                        rejected_count += 1
                    elif pt in (3, 6):  # AppealReceivedPage / AppealSubmittedPage
                        conn.execute(
                            "UPDATE violateVideos SET status='under_review' WHERE profile_id=? AND video_id=?",
                            (profile_id, vid),
                        )
                        conn.execute(
                            "UPDATE accountAppeals SET status='under_review', updated_at=? WHERE profile_id=? AND object_id=?",
                            (now_str, profile_id, vid),
                        )
                        reviewing_count += 1
                except Exception as e:
                    logger.warning("Failed to reconcile appeal status for video %s: %s", vid, e)

            conn.commit()

            # Refresh standing & strikes
            try:
                self.fetch_account_standing(profile_id)
            except Exception as e:
                logger.warning("Failed to refresh account standing in check_appeal_status: %s", e)

            appeals = conn.execute(
                "SELECT * FROM accountAppeals WHERE profile_id=? ORDER BY id DESC",
                (profile_id,),
            ).fetchall()

            return {
                "profile_id": profile_id,
                "appeals_count": len(appeals),
                "resolved_count": resolved_count,
                "rejected_count": rejected_count,
                "reviewing_count": reviewing_count,
                "status": "synchronized",
            }
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

    def precheck_video_content(
        self,
        profile_id: int,
        video_path: str | Path | None = None,
        video_title: str = "",
        item_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Pre-publishes/checks video content against TikTok Community Guidelines and Music Copyright.
        Endpoint: POST https://www.tiktok.com/tiktok/v1/creator/content/check/create
        """
        entitlements.require(Feature.CHANNEL_HEALTH)
        conn = self._get_connection()
        try:
            row = conn.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
            if not row:
                return {"is_safe": False, "copyright_risk": "unknown", "message": "Profile not found"}

            p = dict(row)
            cookies_json = pick_session_cookie(p)  # refreshed browser session first
            cookie_hdr = parse_cookie_header_str(cookies_json)
            ua = p.get("user_agent") or "Mozilla/5.0"

            url = "https://www.tiktok.com/tiktok/v1/creator/content/check/create"
            payload = {
                "title": video_title,
                "item_id": item_id or "",
                "check_type": 1,
            }

            resp = self._request_tiktok_api(
                url,
                cookie_hdr,
                ua,
                profile_id=profile_id,
                method="POST",
                json_data=payload,
                timeout=12,
            )

            chk = resp.get("check_result") or {}
            has_violation = bool(chk.get("has_violation", False))
            risk = chk.get("copyright_risk") or ("high" if has_violation else "low")
            audio_st = chk.get("audio_status") or ("muted" if has_violation else "clear")
            msg = chk.get("message") or (
                "Phát hiện cảnh báo vi phạm bản quyền hoặc nguyên tắc."
                if has_violation
                else "Nội dung an toàn, không phát hiện vi phạm bản quyền hoặc nguyên tắc."
            )

            return {
                "profile_id": profile_id,
                "is_safe": not has_violation,
                "copyright_risk": risk,
                "audio_status": audio_st,
                "message": msg,
                "raw": resp,
            }
        finally:
            conn.close()


__all__ = ["TikTokModerationService", "parse_cookie_header_str"]
