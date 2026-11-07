"""
Deep Analytics & Telemetry Parser for TikTok Creator Studio.
Processes undocumented native telemetry payloads:
- Optimal posting hours & peak follower activity curve.
- FYP SEO keywords & item search terms.
- Second-by-second retention curves & completion rates.
- Real-time traffic source attribution (For You vs Search vs Profile).
- Audience demographics (Countries, Cities, Age, Gender).
- Competitor & peer intelligence (Top creators & videos watched by viewers).
- AI comment summarization (Inspiration, Questions, Sentiments).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def calculate_optimal_post_hours(matrix: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Analyzes a 7-day x 24-hour matrix of follower active history to determine the optimal posting window.

    Each element in `matrix` represents a day containing an array of 24 hourly follower counts (0h to 23h).
    Returns a dict with `peak_hour`, `peak_window` (e.g. '07:00 - 09:00'), `peak_users`, and `hourly_totals`.
    """
    if not matrix or not isinstance(matrix, list):
        return {
            "peak_hour": 12,
            "peak_window": "12:00 - 14:00",
            "peak_users": 0,
            "hourly_totals": [0] * 24,
        }

    hourly_totals = [0] * 24
    valid_days = 0

    for day_item in matrix:
        if not isinstance(day_item, dict):
            continue
        vals = day_item.get("value")
        if isinstance(vals, list) and len(vals) == 24:
            valid_days += 1
            for h in range(24):
                try:
                    hourly_totals[h] += int(vals[h])
                except (ValueError, TypeError):
                    pass

    if valid_days == 0 or max(hourly_totals) == 0:
        return {
            "peak_hour": 12,
            "peak_window": "12:00 - 14:00",
            "peak_users": 0,
            "hourly_totals": [0] * 24,
        }

    # Find the peak single hour
    peak_h = int(max(range(24), key=lambda h: hourly_totals[h]))
    avg_peak_users = int(round(hourly_totals[peak_h] / max(1, valid_days)))

    # Window is 1 hour before to 1 hour after
    start_h = (peak_h - 1) % 24
    end_h = (peak_h + 1) % 24
    peak_window = f"{start_h:02d}:00 - {end_h:02d}:00"

    return {
        "peak_hour": peak_h,
        "peak_window": peak_window,
        "peak_users": avg_peak_users,
        "hourly_totals": [int(round(v / max(1, valid_days))) for v in hourly_totals],
    }


def parse_search_terms(raw_data: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Extracts search keywords driving organic FYP and Search traffic to a video.

    Payload format from `/aweme/v2/data/insight/` with `insigh_type: item_search_terms`.
    """
    if not raw_data or not isinstance(raw_data, dict):
        return []

    items = raw_data.get("value") or []
    if not isinstance(items, list):
        return []

    parsed: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        kw = str(it.get("key") or "").strip()
        if not kw:
            continue
        try:
            val = float(it.get("value") or 0.0)
            pct = round(val * 100.0, 1)
        except (ValueError, TypeError):
            pct = 0.0

        parsed.append({
            "keyword": kw,
            "percentage": pct,
            "raw_value": val,
        })

    return sorted(parsed, key=lambda x: x["percentage"], reverse=True)


def parse_retention_data(
    raw_retention: dict[str, Any] | None, raw_finish: dict[str, Any] | None
) -> dict[str, Any]:
    """Parses second-by-second drop-off curve points and completion rate.

    Payload format from `/aweme/v2/data/insight/` with `video_retention_rate_realtime` and `video_finish_rate_realtime`.
    """
    finish_rate_pct = 0.0
    if raw_finish and isinstance(raw_finish, dict):
        f_val = raw_finish.get("value")
        if isinstance(f_val, (int, float)):
            finish_rate_pct = round(float(f_val) * 100.0, 2)

    points: list[dict[str, Any]] = []
    if raw_retention and isinstance(raw_retention, dict):
        val_obj = raw_retention.get("value") or {}
        raw_list = val_obj.get("list") if isinstance(val_obj, dict) else (raw_retention.get("list") or [])

        if isinstance(raw_list, list):
            for pt in raw_list:
                if not isinstance(pt, dict):
                    continue
                try:
                    ts_ms = int(pt.get("timestamp") or 0)
                    sec = ts_ms // 1000
                    ret = round(float(pt.get("value") or 0.0) * 100.0, 1)
                    points.append({"second": sec, "retention": ret})
                except (ValueError, TypeError):
                    continue

    if finish_rate_pct == 0.0 and points:
        # TikTok answers null for video_finish_rate_realtime (live, 2026-11): the end of the retention curve is
        # the share of viewers still watching at the last second, i.e. the completion rate.
        finish_rate_pct = points[-1]["retention"]

    return {
        "finish_rate": finish_rate_pct,
        "points": points,
    }


def parse_traffic_source_matrix(raw_traffic: dict[str, Any] | None) -> dict[str, float]:
    """Parses traffic source percentages (For You, Search, Personal Profile, Sound, Follow)."""
    if not raw_traffic or not isinstance(raw_traffic, dict):
        return {}

    val_obj = raw_traffic.get("value")
    kv_list = val_obj.get("value") if isinstance(val_obj, dict) else (raw_traffic.get("key_value") or [])
    if not isinstance(kv_list, list):
        return {}

    matrix: dict[str, float] = {}
    for it in kv_list:
        if not isinstance(it, dict):
            continue
        k = str(it.get("key") or "").lower()
        try:
            v = round(float(it.get("value") or 0.0) * 100.0, 1)
        except (ValueError, TypeError):
            v = 0.0

        if "for you" in k:
            matrix["for_you"] = v
        elif "search" in k:
            matrix["search"] = v
        elif "profile" in k:
            matrix["profile"] = v
        elif "follow" in k:
            matrix["following"] = v
        elif "sound" in k:
            matrix["sound"] = v
        else:
            matrix[k] = v

    return matrix


def parse_competitor_intelligence(
    raw_users: dict[str, Any] | None, raw_items: dict[str, Any] | None
) -> dict[str, Any]:
    """Parses peer creators and competitor videos watched by audience.

    Payload format from `/aweme/v2/data/insight/` with `viewer_also_watched_users` and `viewer_also_watched_items`.
    """
    creators: list[dict[str, Any]] = []
    if raw_users and isinstance(raw_users, dict):
        u_list = raw_users.get("value") or []
        if isinstance(u_list, list):
            for u in u_list:
                if not isinstance(u, dict):
                    continue
                avatars = u.get("avatar_thumb", {}).get("url_list") or []
                avatar_url = avatars[0] if avatars else ""
                creators.append({
                    "nickname": str(u.get("nickname") or ""),
                    "unique_id": str(u.get("unique_id") or ""),
                    "follower_count": int(u.get("follower_count") or 0),
                    "avatar_url": avatar_url,
                    "sec_uid": str(u.get("sec_uid") or ""),
                })

    videos: list[dict[str, Any]] = []
    if raw_items and isinstance(raw_items, dict):
        i_list = raw_items.get("value") or []
        if isinstance(i_list, list):
            for it in i_list:
                if not isinstance(it, dict):
                    continue
                stats = it.get("statistics") or {}
                vid_obj = it.get("video") or {}
                play_urls = vid_obj.get("play_addr", {}).get("url_list") or []
                download_url = play_urls[0] if play_urls else ""
                covers = vid_obj.get("cover", {}).get("url_list") or []
                cover_url = covers[0] if covers else ""

                videos.append({
                    "aweme_id": str(it.get("aweme_id") or it.get("id") or ""),
                    "desc": str(it.get("desc") or ""),
                    "play_count": int(stats.get("play_count") or 0),
                    "like_count": int(stats.get("digg_count") or 0),
                    "comment_count": int(stats.get("comment_count") or 0),
                    "share_count": int(stats.get("share_count") or 0),
                    "download_url": download_url,
                    "cover_url": cover_url,
                })

    return {
        "top_creators": creators,
        "top_videos": videos,
    }


def parse_audience_demographics(raw_insights: dict[str, Any] | None) -> dict[str, Any]:
    """Parses demographics payload from `/tiktok/v1/analytics/insights/`.

    Extracts follower and viewer countries, cities, gender, age distribution.
    """
    if not raw_insights or not isinstance(raw_insights, dict):
        return {}

    # Follower Countries
    countries: list[dict[str, Any]] = []
    f_country_obj = raw_insights.get("analytics_follower_country_city_percent") or {}
    raw_countries = f_country_obj.get("key_value") or []
    if isinstance(raw_countries, list):
        for c in raw_countries:
            if not isinstance(c, dict):
                continue
            c_name = str(c.get("country_name") or "Other")
            c_pct = round(float(c.get("country_percent") or 0.0) * 100.0, 1)

            cities: list[dict[str, Any]] = []
            for city_group in c.get("key_value") or []:
                for city_item in city_group.get("key_value") or []:
                    if isinstance(city_item, dict) and "key" in city_item:
                        cities.append({
                            "city": str(city_item.get("key")),
                            "percentage": round(float(city_item.get("value") or 0.0) * 100.0, 1),
                        })

            countries.append({
                "country": c_name,
                "percentage": c_pct,
                "cities": cities,
            })

    # Follower Age
    ages: list[dict[str, Any]] = []
    f_age_obj = raw_insights.get("analytics_follower_age_percent") or {}
    raw_ages = f_age_obj.get("key_value") or []
    if isinstance(raw_ages, list):
        for a in raw_ages:
            if isinstance(a, dict) and "key" in a:
                ages.append({
                    "range": str(a.get("key")),
                    "percentage": round(float(a.get("value") or 0.0) * 100.0, 1),
                })

    # Follower Gender
    genders: list[dict[str, Any]] = []
    f_gender_obj = raw_insights.get("analytics_follower_gender_percent") or {}
    raw_genders = f_gender_obj.get("key_value") or []
    if isinstance(raw_genders, list):
        for g in raw_genders:
            if isinstance(g, dict) and "key" in g:
                genders.append({
                    "gender": str(g.get("key")),
                    "percentage": round(float(g.get("value") or 0.0) * 100.0, 1),
                })

    # Viewer Total
    viewer_total = 0
    v_total_obj = raw_insights.get("analytics_viewer_total_viewer") or {}
    if isinstance(v_total_obj, dict) and "total" in v_total_obj:
        viewer_total = int(v_total_obj.get("total", {}).get("value") or 0)

    return {
        "follower_countries": countries,
        "follower_ages": ages,
        "follower_genders": genders,
        "viewer_total_7d": viewer_total,
    }


def parse_ai_comments(raw_ai: dict[str, Any] | None) -> dict[str, Any]:
    """Parses AI comment summary from `/tiktok/v1/creator/ai_comment/analytics_overview`."""
    if not raw_ai or not isinstance(raw_ai, dict):
        return {}

    categories = []
    for cat in raw_ai.get("category_list") or []:
        if isinstance(cat, dict):
            categories.append({
                "name": str(cat.get("name") or ""),
                "description": str(cat.get("description") or ""),
                "comment_count": int(cat.get("comment_count") or 0),
            })

    topic_info = raw_ai.get("comment_topic") or {}
    return {
        "eligible": bool(raw_ai.get("eligible_video")),
        "categories": categories,
        "topics_description": str(topic_info.get("description") or ""),
    }

