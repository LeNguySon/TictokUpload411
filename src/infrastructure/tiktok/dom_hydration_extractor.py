"""
TikTok Public Page DOM Hydration Extractor.
Extracts user stats, channel metadata, and follower counts from __UNIVERSAL_DATA_FOR_REHYDRATION__ or SIGI_STATE.
Learned from Gloglin2609/engine/tiktok/cookie_extractor.py.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_RE_REHYDRATION = re.compile(
    r'<script[^>]*id=["\']__UNIVERSAL_DATA_FOR_REHYDRATION__["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
_RE_SIGI = re.compile(
    r'<script[^>]*id=["\']SIGI_STATE["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


class TikTokDomHydrationExtractor:
    """
    Parses live or public SSR HTML from TikTok channel pages without headless browser overhead.
    """

    def extract(self, html: str) -> dict[str, Any] | None:
        """
        Parses TikTok hydration JSON from HTML source.
        Returns dict with channel stats or None if no valid hydration data was found.
        """
        if not html:
            return None

        m = _RE_REHYDRATION.search(html)
        if not m:
            m = _RE_SIGI.search(html)
        if not m:
            return None

        raw_text = m.group(1).strip()
        if not raw_text:
            return None

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            try:
                data = json.loads(raw_text.strip().strip(";"))
            except Exception as e:
                logger.debug("Failed to decode hydration JSON: %s", e)
                return None

        candidates: list[dict[str, Any]] = []

        # Recursively search for userInfo, user, stats in payload
        def _deep_find(obj: Any, depth: int = 0) -> None:
            if depth > 6 or not isinstance(obj, dict):
                return
            for key in ("userInfo", "user", "userDetail"):
                if key in obj and isinstance(obj[key], dict):
                    inner = obj[key]
                    if "user" in inner and isinstance(inner["user"], dict):
                        candidate = dict(inner["user"])
                        if isinstance(inner.get("stats"), dict):
                            candidate["_bound_stats"] = inner["stats"]
                        candidates.append(candidate)
                    elif "uniqueId" in inner:
                        candidate = dict(inner)
                        if isinstance(obj.get("stats"), dict):
                            candidate["_bound_stats"] = obj["stats"]
                        candidates.append(candidate)

            for v in obj.values():
                if isinstance(v, dict):
                    _deep_find(v, depth + 1)
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict):
                            _deep_find(item, depth + 1)

        _deep_find(data)

        # Fallback to well-known path in SIGI_STATE or default scope
        if not candidates:
            # Check SIGI_STATE: UserModule.users / stats
            user_module = data.get("UserModule", {})
            users = user_module.get("users", {})
            stats_dict = user_module.get("stats", {})
            if users and isinstance(users, dict):
                first_uid = next(iter(users))
                candidate = dict(users[first_uid])
                if first_uid in stats_dict:
                    candidate["_bound_stats"] = stats_dict[first_uid]
                candidates.append(candidate)

        if not candidates:
            # Check __DEFAULT_SCOPE__["webapp.user-detail"]
            scope = data.get("__DEFAULT_SCOPE__", data)
            webapp = scope.get("webapp.user-detail") or {}
            if isinstance(webapp, dict):
                u_info = webapp.get("userInfo", {})
                if isinstance(u_info, dict) and "user" in u_info:
                    candidate = dict(u_info["user"])
                    if "stats" in u_info:
                        candidate["_bound_stats"] = u_info["stats"]
                    candidates.append(candidate)

        if not candidates:
            return None

        best = candidates[0]
        stats = best.get("_bound_stats", {})

        unique_id = str(best.get("uniqueId") or "")
        nickname = str(best.get("nickname") or unique_id)
        avatar_url = str(best.get("avatarLarger") or best.get("avatarMedium") or best.get("avatarThumb") or "")
        signature = str(best.get("signature") or best.get("bio") or "")
        region = str(best.get("region") or best.get("country") or "")
        privacy = 1 if (best.get("privateAccount") or best.get("secret")) else 0

        follower_count = int(stats.get("followerCount", 0))
        following_count = int(stats.get("followingCount", 0))
        heart_count = int(stats.get("heartCount") or stats.get("heart") or 0)
        video_count = int(stats.get("videoCount", 0))

        return {
            "uniqueId": unique_id,
            "nickname": nickname,
            "avatarUrl": avatar_url,
            "signature": signature,
            "region": region,
            "privacy": privacy,
            "followerCount": follower_count,
            "followingCount": following_count,
            "heartCount": heart_count,
            "videoCount": video_count,
            "raw": data,
        }
