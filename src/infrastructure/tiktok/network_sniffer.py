"""
TikTok Passive Network Sniffer.
Intercepts and parses TikTok API payloads passively from CDP / browser network responses.
Learned from Gloglin2609/engine/tiktok/network_sniffer.py.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.application.signals.app_signals import AppSignalBus
from src.infrastructure.database.connection import db_session

logger = logging.getLogger(__name__)


class TikTokNetworkSniffer:
    """
    Passively parses intercepted TikTok API JSON payloads and updates SQLite profiles
    and statisticTable without issuing separate network requests.
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

        # 1. User detail / Channel stats
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

        # 2. Creator Dashboard / Revenue / Rewards
        if any(
            ep in url_lower
            for ep in (
                "/api/creator/dashboard/overview",
                "/creator-center/api/income/overview",
                "/creator-center/api/creator/rewards",
            )
        ):
            overview = data.get("overview") or data.get("data") or data
            if isinstance(overview, dict):
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

        # Write profile updates if any
        if updates:
            self._update_profile_row(profile_id, updates)

        # 3. Post item list / Videos & Views
        if "/api/post/item_list" in url_lower or "/api/creator/item/list" in url_lower:
            items = data.get("itemList") or data.get("items") or data.get("item_list")
            if isinstance(items, list) and items:
                self._upsert_video_items(profile_id, items)
                handled = True

        if handled and self.signal_bus:
            self.signal_bus.profile_updated.emit(profile_id, updates)

        return handled

    def _update_profile_row(self, profile_id: int, updates: dict[str, Any]) -> None:
        """Atomically updates columns in profiles table."""
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

    def _upsert_video_items(self, profile_id: int, items: list[dict[str, Any]]) -> None:
        """Upserts video performance items into statisticTable."""
        sql = """
        INSERT INTO statisticTable (
            profile_id, id_video, title, views, likes, comments, shares, status, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP)
        ON CONFLICT(profile_id, id_video) DO UPDATE SET
            title = COALESCE(excluded.title, statisticTable.title),
            views = excluded.views,
            likes = excluded.likes,
            comments = excluded.comments,
            shares = excluded.shares,
            updated_at = CURRENT_TIMESTAMP;
        """
        records = []
        for it in items:
            vid_id = str(it.get("id") or it.get("video_id") or "")
            if not vid_id:
                continue
            title = str(it.get("desc") or it.get("title") or "")
            stats = it.get("stats", {})
            views = int(stats.get("playCount") or stats.get("views") or 0)
            likes = int(stats.get("diggCount") or stats.get("likes") or 0)
            comments = int(stats.get("commentCount") or stats.get("comments") or 0)
            shares = int(stats.get("shareCount") or stats.get("shares") or 0)
            records.append((profile_id, vid_id, title, views, likes, comments, shares))

        if records:
            try:
                with db_session(self.db_path) as conn:
                    conn.executemany(sql, records)
                logger.info("Sniffer upserted %d videos into statisticTable for profile %s", len(records), profile_id)
            except Exception as e:
                logger.error("Failed to upsert videos into statisticTable for profile %s: %s", profile_id, e)
