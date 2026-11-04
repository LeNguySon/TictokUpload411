"""
Low View Alert Heuristic Engine.
Learned from Gloglin2609/engine/tiktok/low_view_alert.py.

Analyzes the most recent video publications to detect consecutive low-view patterns
(an indicator of shadowban, reach penalty, or unoriginal content suppression).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from statistics import median
from typing import Any

MAX_VIDEOS = 15
REQUIRED_CONSECUTIVE = 5


def _parse_pub_time(video: Mapping[str, Any]) -> float | None:
    val = video.get("date_upload") or video.get("createTime") or video.get("created_at")
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val) if math.isfinite(val) and val > 0 else None
    if not isinstance(val, str) or not val.strip():
        return None
    try:
        parsed = datetime.fromisoformat(val.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.timestamp()
    except (ValueError, OverflowError, OSError):
        return None


def analyze_low_view_alert(videos: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """
    Analyzes up to 15 newest publications to identify consecutive low-view drops.
    An alert is triggered when at least 5 consecutive newest videos have views
    below 10% of channel median and under 100 views.
    """
    observations = []
    for v in videos:
        if not isinstance(v, Mapping):
            continue
        item = dict(v)
        published = _parse_pub_time(item)
        observations.append((published, item))

    # Sort newest publications first
    observations.sort(key=lambda x: x[0] if x[0] is not None else -math.inf, reverse=True)
    sample = observations[:MAX_VIDEOS]

    if not sample:
        return {
            "ok": False,
            "alert": False,
            "risk_score": 0.0,
            "message": "Chưa có dữ liệu video để phân tích.",
            "coverage": {"sampled_count": 0, "consecutive_low_views": 0, "median_views": 0},
        }

    counts: list[int] = []
    for _, it in sample:
        v_count = it.get("views") or it.get("playCount") or 0
        try:
            counts.append(int(v_count))
        except (ValueError, TypeError):
            counts.append(0)

    typical = median(counts) if counts else 0
    flags = [(c * 10 < typical and c < 100) if typical > 0 else (c < 100) for c in counts]

    consecutive = 0
    for is_low in flags:
        if not is_low:
            break
        consecutive += 1

    alert = consecutive >= REQUIRED_CONSECUTIVE
    risk = round((sum(flags) / len(sample)) * 100.0, 2) if sample else 0.0

    if alert:
        msg = f"Cảnh báo Flop: Có {consecutive} video mới nhất liên tiếp có lượt xem dưới 10% trung vị kênh ({int(typical)} views) và dưới 100 views."
    elif consecutive > 0:
        msg = f"Theo dõi: Phát hiện {consecutive} video liên tiếp dưới ngưỡng bình thường."
    else:
        msg = "Trạng thái lành mạnh: Phân phối lượt xem đồng đều, không có dấu hiệu bóp tương tác."

    return {
        "ok": True,
        "alert": alert,
        "risk_score": risk,
        "message": msg,
        "coverage": {
            "sampled_count": len(sample),
            "known_count": len(counts),
            "median_views": typical,
            "consecutive_low_views": consecutive,
        },
    }
