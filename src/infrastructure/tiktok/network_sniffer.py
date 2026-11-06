"""
TikTok Passive Network Sniffer.
Intercepts and parses TikTok API payloads passively from CDP / browser network responses.
Learned from Gloglin2609/engine/tiktok/network_sniffer.py and SamMonny SDK.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.application.signals.app_signals import AppSignalBus
from src.infrastructure.database.connection import db_session

logger = logging.getLogger(__name__)

# Name given by ProfileRepository.create() when the user did not choose one.
_AUTO_PROFILE_NAME = re.compile(r"^Profile_[0-9A-Za-z-]{8}$")  # f"Profile_{uuid[:8]}"


class TikTokNetworkSniffer:
    """
    Passively parses intercepted TikTok API JSON payloads and updates SQLite profiles,
    statisticTable, videoTables, and violateVideos without issuing separate network requests.
    """

    def __init__(
        self,
        db_path: Path | str | None = None,
        signal_bus: AppSignalBus | None = None,
    ) -> None:
        self.db_path = Path(db_path) if db_path else Path("data/app.db")
        self.signal_bus = signal_bus or AppSignalBus.instance()

    def process_api_response(
        self,
        profile_id: int,
        url: str,
        data: dict[str, Any],
    ) -> bool:
        """
        Parses TikTok API response and synchronizes metrics to SQLite.
        Returns True if recognized and processed, False otherwise.
        """
        if not isinstance(data, dict):
            return False

        url_lower = url.lower()
        handled = False
        updates: dict[str, Any] = {}

        now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        # 1. User detail / Channel stats (/api/user/detail/)
        if "/api/user/detail" in url_lower:
            user_info = data.get("userInfo", {})
            user = user_info.get("user", {})
            stats = user_info.get("stats", {})

            if user or stats:
                if "uniqueId" in user:
                    updates["name"] = str(user["uniqueId"])
                    updates["username_on_tiktok"] = str(user["uniqueId"])
                if "nickname" in user:
                    updates["nickname"] = str(user["nickname"])
                if "id" in user:
                    updates["tiktok_user_id"] = str(user["id"])
                if "secUid" in user:
                    updates["sec_uid"] = str(user["secUid"])
                if "avatarLarger" in user or "avatarMedium" in user or "avatarThumb" in user:
                    updates["avatar_url"] = str(
                        user.get("avatarLarger") or user.get("avatarMedium") or user.get("avatarThumb")
                    )
                if "signature" in user or "bio" in user:
                    updates["bio"] = str(user.get("signature") or user.get("bio"))
                if "region" in user or "country" in user:
                    updates["country"] = str(user.get("region") or user.get("country"))
                if "privateAccount" in user or "secret" in user:
                    updates["privacy"] = 1 if (user.get("privateAccount") or user.get("secret")) else 0

                if "followerCount" in stats:
                    updates["total_followers"] = int(stats["followerCount"])
                if "followingCount" in stats:
                    updates["total_following"] = int(stats["followingCount"])
                if "heartCount" in stats or "heart" in stats:
                    updates["total_likes"] = int(stats.get("heartCount") or stats.get("heart") or 0)
                if "videoCount" in stats:
                    updates["total_videos"] = int(stats["videoCount"])

                updates["statistic_date_update"] = now_str
                handled = True

        # 2. Creator Dashboard / Revenue / Rewards / Insights 2026
        if any(
            ep in url_lower
            for ep in (
                "/api/creator/dashboard/overview",
                "/creator-center/api/income/overview",
                "/creator-center/api/creator/rewards",
                "/tiktok/v1/analytics/insights",
                "/aweme/v2/data/insight",
            )
        ):
            overview = data.get("overview") or data.get("data") or data
            if isinstance(overview, dict):
                # TikTok Studio 2026 Analytics Insights
                if "analytics_overview_rewards" in overview:
                    rew = overview["analytics_overview_rewards"]
                    msg = rew.get("message") or {}
                    st = msg.get("status")
                    if st == 2:
                        # Status 2: Not enrolled in rewards / Ineligible
                        updates["money_earned"] = 0.0
                        updates["rpm"] = 0.0
                    elif st == 1 or st == 0:
                        tot = rew.get("total") or {}
                        updates["money_earned"] = float(tot.get("value") or 0.0)
                        updates["rpm"] = float(rew.get("rpm", {}).get("value") or 0.0)

                if "analytics_overview_views" in overview:
                    v_info = overview["analytics_overview_views"]
                    v_list = v_info.get("list", {}).get("value") or []
                    if v_list:
                        sum_vv = sum(int(item.get("value") or 0) for item in v_list if isinstance(item, dict))
                        if sum_vv > 0:
                            updates["views_month"] = sum_vv
                            updates["total_views"] = sum_vv

                # Traffic Source Matrix & Shadowban Detection
                if "analytics_overview_traffic_source" in overview:
                    ts_info = overview["analytics_overview_traffic_source"]
                    kv_list = ts_info.get("key_value") or []
                    ts_dict: dict[str, float] = {}
                    for it in kv_list:
                        if isinstance(it, dict):
                            k = str(it.get("key", "")).lower()
                            v = float(it.get("value") or 0.0)
                            if "for you" in k:
                                ts_dict["for_you"] = round(v * 100.0, 1)
                            elif "search" in k:
                                ts_dict["search"] = round(v * 100.0, 1)
                            elif "profile" in k:
                                ts_dict["profile"] = round(v * 100.0, 1)
                            elif "follow" in k:
                                ts_dict["following"] = round(v * 100.0, 1)
                            elif "sound" in k:
                                ts_dict["sound"] = round(v * 100.0, 1)

                    if ts_dict:
                        import json as _json
                        updates["traffic_source_json"] = _json.dumps(ts_dict)
                        fyf = ts_dict.get("for_you", 0.0)
                        if fyf >= 70.0:
                            updates["shadowban_status"] = "safe"
                            updates["shadowban_reasons"] = ""
                        elif fyf < 20.0:
                            updates["shadowban_status"] = "shadowban"
                            updates["shadowban_reasons"] = "Lượng người xem Dành cho bạn (FYF) tụt dưới 20%. Nghi vấn tài khoản dính shadowban hoặc hạn chế phân phối."
                        else:
                            updates["shadowban_status"] = "warning"
                            updates["shadowban_reasons"] = "Lượng phân phối Dành cho bạn ở mức vừa phải (20-70%)."

                # Hourly Activity & Optimal Posting Hour
                if "analytics_viewer_active_hours" in overview:
                    ah_info = overview["analytics_viewer_active_hours"]
                    days_list = ah_info.get("list") or []
                    hourly_totals: dict[int, int] = {}
                    for day_data in days_list:
                        inner_list = day_data.get("list", {}).get("key_value") or []
                        for h_item in inner_list:
                            if isinstance(h_item, dict):
                                try:
                                    h_idx = int(h_item.get("key", 0))
                                    h_val = int(h_item.get("value", 0))
                                    hourly_totals[h_idx] = hourly_totals.get(h_idx, 0) + h_val
                                except (ValueError, TypeError):
                                    continue
                    if hourly_totals:
                        best_h = max(hourly_totals.items(), key=lambda x: x[1])[0]
                        updates["optimal_hour"] = int(best_h)

                # Audience Retention: New Viewers vs Returning Viewers
                new_v_data = overview.get("new_viewer")
                ret_v_data = overview.get("returning_viewer")
                if new_v_data is not None or ret_v_data is not None:
                    total_new = 0
                    total_returning = 0
                    if isinstance(new_v_data, list):
                        total_new = sum(int(it.get("value") or 0) for it in new_v_data if isinstance(it, dict))
                    if isinstance(ret_v_data, list):
                        total_returning = sum(int(it.get("value") or 0) for it in ret_v_data if isinstance(it, dict))

                    tot_all = total_new + total_returning
                    ret_ratio = round((total_returning / tot_all) * 100.0, 1) if tot_all > 0 else 0.0
                    import json as _json
                    updates["retention_stats_json"] = _json.dumps({
                        "total_new": total_new,
                        "total_returning": total_returning,
                        "returning_ratio": ret_ratio,
                    })

                # aweme/v2/data/insight fallback
                if "user_rewards_data" in overview:
                    urd = overview["user_rewards_data"]
                    if urd.get("status") == 2 or urd.get("est_rewards", {}).get("status") == 2:
                        updates["money_earned"] = 0.0
                        updates["rpm"] = 0.0

                if "vv_history" in overview and isinstance(overview["vv_history"], list):
                    vv_sum = sum(int(it.get("value") or 0) for it in overview["vv_history"] if isinstance(it, dict))
                    if vv_sum > 0:
                        updates["views_month"] = vv_sum
                        updates["total_views"] = vv_sum

                # Legacy keys
                if "money_earned" in overview or "total_revenue" in overview or "revenue" in overview:
                    updates["money_earned"] = float(
                        overview.get("money_earned") or overview.get("total_revenue") or overview.get("revenue") or 0.0
                    )
                if "rpm" in overview or "estimated_rpm" in overview:
                    updates["rpm"] = float(overview.get("rpm") or overview.get("estimated_rpm") or 0.0)
                if "balance" in overview:
                    updates["balance"] = float(overview.get("balance") or 0.0)
                if "qualified_views" in overview or "views" in overview:
                    updates["total_views"] = int(overview.get("qualified_views") or overview.get("views") or 0)
                if "currency" in overview:
                    updates["currency"] = str(overview.get("currency") or "USD")
                if "date_reapply" in overview or "reapply_date" in overview:
                    updates["date_reapply"] = str(overview.get("date_reapply") or overview.get("reapply_date") or "")
                if "state_kyc" in overview or "kyc_status" in overview:
                    updates["state_kyc"] = str(overview.get("state_kyc") or overview.get("kyc_status") or "")

                updates["statistic_date_update"] = now_str
                handled = True

        # 2b. Counter / HashCount (/tiktokstudio/api/web/counter/getHashCount)
        if "/counter/gethashcount" in url_lower:
            if "item_count" in data:
                updates["total_videos"] = int(data["item_count"])
            if "like_count" in data:
                updates["total_likes"] = int(data["like_count"])
            updates["statistic_date_update"] = now_str
            handled = True

        # 3. Account Standing & Strikes (/api/creator/account/standing/)
        if "/api/creator/account/standing" in url_lower:
            standing = data.get("standing_level") or data.get("account_standing") or data.get("standing") or "Good"
            strikes = int(data.get("active_strikes") or data.get("strike_count") or data.get("strikes") or 0)
            updates["account_standing"] = str(standing)
            updates["strike_count"] = strikes
            updates["statistic_date_update"] = now_str
            handled = True

        # 4. Violations & Warnings (/api/creator/violation/ or /creator-center/api/violation/)
        if "/api/creator/violation" in url_lower or "/creator-center/api/violation" in url_lower:
            if "history" in url_lower:
                penalty_points = int(data.get("total_penalty_points") or data.get("penalty_points") or 0)
                expire_date = str(data.get("penalty_expire_date") or data.get("expire_date") or "")
                updates["total_penalty_points"] = penalty_points
                if expire_date:
                    updates["penalty_expire_date"] = expire_date
                updates["statistic_date_update"] = now_str
                handled = True
            else:
                violations = data.get("violations") or data.get("violation_list") or []
                strike_count = int(
                    data.get("active_strikes")
                    or data.get("strike_count")
                    or (len(violations) if isinstance(violations, list) else 0)
                )
                standing = str(
                    data.get("standing_level")
                    or data.get("account_standing")
                    or ("Good" if strike_count == 0 else ("Warning" if strike_count < 3 else "Risk"))
                )
                latest_appeal_date = None

                if isinstance(violations, list) and violations:
                    with db_session(self.db_path) as conn:
                        for v in violations:
                            if not isinstance(v, dict):
                                continue
                            v_id = str(v.get("id") or v.get("item_id") or v.get("video_id") or "")
                            if not v_id:
                                continue
                            v_title = str(v.get("title") or v.get("item_title") or "Video vi phạm")
                            v_viol_title = str(
                                v.get("violation_title") or v.get("reason") or "Vi phạm Nguyên tắc Cộng đồng"
                            )
                            v_desc = str(
                                v.get("violation_reason") or v.get("violate_description") or v.get("description") or ""
                            )
                            post_d = str(v.get("create_time") or v.get("video_posted_date") or "")
                            appeal_d = str(v.get("appeal_deadline") or v.get("appeal_date") or "")
                            if appeal_d:
                                latest_appeal_date = appeal_d
                            status = str(v.get("status") or "pending")

                            conn.execute(
                                """
                                INSERT INTO violateVideos (
                                    profile_id, video_id, title, violate_title, violate_description,
                                    video_posted_date, appeal_date, status, created_at
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                                ON CONFLICT(profile_id, video_id) DO UPDATE SET
                                    title = excluded.title,
                                    violate_title = excluded.violate_title,
                                    violate_description = excluded.violate_description,
                                    video_posted_date = excluded.video_posted_date,
                                    appeal_date = excluded.appeal_date,
                                    status = excluded.status;
                                """,
                                (profile_id, v_id, v_title, v_viol_title, v_desc, post_d, appeal_d, status),
                            )

                if not latest_appeal_date and (data.get("appeal_deadline") or data.get("appeal_date")):
                    latest_appeal_date = str(data.get("appeal_deadline") or data.get("appeal_date"))

                updates["strike_count"] = strike_count
                updates["account_standing"] = standing
                if latest_appeal_date:
                    updates["appealViolateDate"] = latest_appeal_date
                if violations:
                    updates["ttl_violations"] = json.dumps(violations, ensure_ascii=False)
                updates["statistic_date_update"] = now_str
                handled = True

        # 5. Post item list / Videos & Views (/api/post/item_list, /api/creator/item/list, /manage/item_list/v1)
        if "/api/post/item_list" in url_lower or "/api/creator/item/list" in url_lower or "/manage/item_list/v1" in url_lower:
            items = data.get("creator_item_list") or data.get("itemList") or data.get("items") or data.get("item_list")
            if isinstance(items, list) and items:
                # Extract embedded author information if present in first item
                first_item = items[0] if isinstance(items[0], dict) else {}
                author = first_item.get("author") or {}
                author_stats = first_item.get("authorStats") or first_item.get("author_stats") or {}

                if author:
                    if "uniqueId" in author:
                        updates["name"] = str(author["uniqueId"])
                        updates["username_on_tiktok"] = str(author["uniqueId"])
                    if "nickname" in author:
                        updates["nickname"] = str(author["nickname"])
                    if "id" in author:
                        updates["tiktok_user_id"] = str(author["id"])
                    if "avatarThumb" in author or "avatarLarger" in author or "avatarMedium" in author:
                        updates["avatar_url"] = str(
                            author.get("avatarThumb") or author.get("avatarLarger") or author.get("avatarMedium")
                        )
                    if "privateAccount" in author or "secret" in author:
                        updates["privacy"] = 1 if (author.get("privateAccount") or author.get("secret")) else 0

                if author_stats:
                    if "followerCount" in author_stats:
                        updates["total_followers"] = int(author_stats["followerCount"])
                    if "followingCount" in author_stats:
                        updates["total_following"] = int(author_stats["followingCount"])
                    if "heartCount" in author_stats or "heart" in author_stats:
                        updates["total_likes"] = int(author_stats.get("heartCount") or author_stats.get("heart") or 0)
                    if "videoCount" in author_stats:
                        updates["total_videos"] = int(author_stats["videoCount"])

                # Dual-table persistence (statisticTable + videoTables) & 30-day views calculation
                item_metrics = self._upsert_video_items(profile_id, items)
                updates.update(item_metrics)
                updates["statistic_date_update"] = now_str
                handled = True

        # Write profile updates if any
        if updates:
            self._update_profile_row(profile_id, updates)

        if handled and self.signal_bus:
            self.signal_bus.profile_updated.emit(profile_id, updates)

        return handled

    def _update_profile_row(self, profile_id: int, updates: dict[str, Any]) -> None:
        """Atomically updates columns in profiles table.

        The TikTok handle goes to username_on_tiktok; the profile `name` is the user's own label and is
        only filled in when it is empty or still the repository's auto-generated "Profile_xxxxxxxx".
        """
        if not updates:
            return
        if "name" in updates:
            try:
                with db_session(self.db_path, write=False) as conn:
                    row = conn.execute("SELECT name FROM profiles WHERE id = ?;", (profile_id,)).fetchone()
                current = (row["name"] if row else "") or ""
            except Exception:
                current = "?"  # unknown -> do not risk overwriting
            if current and not _AUTO_PROFILE_NAME.match(current):
                updates.pop("name")
        if not updates:
            return
        set_clauses = [f"{k} = ?" for k in updates.keys()]
        sql = f"UPDATE profiles SET {', '.join(set_clauses)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?;"
        params = list(updates.values()) + [profile_id]

        try:
            with db_session(self.db_path) as conn:
                conn.execute(sql, tuple(params))
            logger.info("TikTok passive sniffer updated profile %s with %d fields", profile_id, len(updates))
        except Exception as e:
            logger.error("Failed to update profile %s from sniffer: %s", profile_id, e)

    def _upsert_video_items(self, profile_id: int, items: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Upserts video performance items into both statisticTable and videoTables.
        Calculates 30-day views (views_month) and total observed views.
        """
        now_ts = int(time.time())
        cutoff_30d = now_ts - (30 * 86400)
        month_views = 0
        total_observed_views = 0

        stat_sql = """
        INSERT INTO statisticTable (
            profile_id, id_video, title, views, likes, comments, shares, engagement_rate, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(profile_id, id_video) DO UPDATE SET
            title = COALESCE(excluded.title, statisticTable.title),
            views = excluded.views,
            likes = excluded.likes,
            comments = excluded.comments,
            shares = excluded.shares,
            engagement_rate = excluded.engagement_rate,
            updated_at = CURRENT_TIMESTAMP;
        """

        video_sql = """
        INSERT INTO videoTables (
            profile_id, video_id, title, views, likes, comments, shares, engagement_rate,
            duration, display, thumbnail_url, allow_comment, allow_duet, allow_stitch,
            is_pinned, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP)
        ON CONFLICT(profile_id, video_id) DO UPDATE SET
            title = COALESCE(excluded.title, videoTables.title),
            views = excluded.views,
            likes = excluded.likes,
            comments = excluded.comments,
            shares = excluded.shares,
            engagement_rate = excluded.engagement_rate,
            duration = excluded.duration,
            display = excluded.display,
            thumbnail_url = excluded.thumbnail_url,
            allow_comment = excluded.allow_comment,
            allow_duet = excluded.allow_duet,
            allow_stitch = excluded.allow_stitch,
            is_pinned = excluded.is_pinned,
            status = 'active';
        """

        stat_records = []
        video_records = []

        for it in items:
            if not isinstance(it, dict):
                continue
            vid_id = str(it.get("id") or it.get("item_id") or it.get("video_id") or "")
            if not vid_id:
                continue
            title = str(it.get("desc") or it.get("item_title") or it.get("title") or "")
            create_time_val = it.get("createTime") or it.get("create_time") or it.get("post_time") or 0
            try:
                create_time = int(create_time_val)
            except (ValueError, TypeError):
                create_time = 0

            stats = it.get("statistics") or it.get("stats") or it.get("item_stats") or {}
            views = int(stats.get("views") or stats.get("playCount") or stats.get("play_count") or it.get("views") or 0)
            likes = int(stats.get("likes") or stats.get("diggCount") or stats.get("digg_count") or it.get("likes") or 0)
            comments = int(
                stats.get("comments")
                or stats.get("commentCount")
                or stats.get("comment_count")
                or it.get("comments")
                or 0
            )
            shares = int(
                stats.get("shares") or stats.get("shareCount") or stats.get("share_count") or it.get("shares") or 0
            )

            eng_rate = round(((likes + comments + shares) / max(1, views)) * 100, 2)

            if create_time >= cutoff_30d:
                month_views += views
            total_observed_views += views

            stat_records.append((profile_id, vid_id, title, views, likes, comments, shares, eng_rate))

            raw_video = it.get("video")
            video_obj: dict[str, Any] = raw_video if isinstance(raw_video, dict) else {}
            duration = int(video_obj.get("duration") or it.get("duration") or 0)
            thumbnail = str(
                video_obj.get("cover")
                or video_obj.get("originCover")
                or it.get("cover")
                or it.get("thumbnail_url")
                or ""
            )
            raw_display = it.get("display")
            display = int(
                raw_display
                if raw_display is not None
                else (it.get("privacy_type") or it.get("privacy") or 1)
            )

            raw_control = it.get("item_control")
            control: dict[str, Any] = raw_control if isinstance(raw_control, dict) else {}
            allow_comment = 1 if control.get("can_comment", True) else 0
            allow_duet = 1 if control.get("can_duet", True) else 0
            allow_stitch = 1 if control.get("can_stitch", True) else 0
            is_pinned = 1 if (it.get("is_top") or it.get("is_pinned")) else 0

            video_records.append(
                (
                    profile_id,
                    vid_id,
                    title,
                    views,
                    likes,
                    comments,
                    shares,
                    eng_rate,
                    duration,
                    display,
                    thumbnail,
                    allow_comment,
                    allow_duet,
                    allow_stitch,
                    is_pinned,
                )
            )

        try:
            with db_session(self.db_path) as conn:
                if stat_records:
                    conn.executemany(stat_sql, stat_records)
                if video_records:
                    conn.executemany(video_sql, video_records)
            logger.info(
                "Sniffer upserted %d videos into statisticTable & videoTables for profile %s (month_views=%d)",
                len(stat_records),
                profile_id,
                month_views,
            )
        except Exception as e:
            logger.error("Failed to upsert videos for profile %s: %s", profile_id, e)

        return {
            "views_month": month_views,
            "total_views": total_observed_views,
        }


def attach_playwright_sniffer(
    context_or_page: Any,
    profile_id: int,
    db_path: Path | str | None = None,
    signal_bus: AppSignalBus | None = None,
) -> None:
    """Attach response listener to Playwright context or page for passive live sniffing."""
    sniffer = TikTokNetworkSniffer(db_path=db_path, signal_bus=signal_bus)

    def on_response(response: Any) -> None:
        try:
            url = getattr(response, "url", "")
            if not url or not any(d in url for d in ("tiktok.com", "tiktokv.com", "byteoversea.com", "ibytedtos.com")):
                return
            if not any(
                x in url
                for x in (
                    "/api/",
                    "/creator-center/api/",
                    "/passport/web/",
                    "/aweme/v1/",
                    "/traffic_source",
                    "/service/2/",
                    "/item/insight",
                    "/item/detail",
                )
            ):
                return
            status = getattr(response, "status", 0)
            if status != 200:
                return

            try:
                body = response.json()
                if isinstance(body, dict):
                    sniffer.process_api_response(profile_id, url, body)
            except Exception as ignored:
                logger.debug("on_response: ignored error: %s", ignored)
        except Exception as exc:
            logger.debug("Passive sniffer error on response: %s", exc)

    try:
        context_or_page.on("response", on_response)
        logger.info("Attached passive Playwright sniffer for profile %s", profile_id)
    except Exception as exc:
        logger.debug("Could not attach sniffer listener: %s", exc)
