"""
Measured best posting hour of a channel.

``profiles.optimal_hour`` has a schema default of 12 and the active-hours parser returns a "12:00" placeholder
(peak_users = 0) when TikTok sends no data, so neither proves anything. Only ``optimal_posting_hours_json`` with
followers actually online at the peak (``peak_users > 0``) is a measurement.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MeasuredPostingHour:
    hour: int
    window: str
    peak_users: int


def peak_window(hour: int) -> str:
    """The 2-hour window around a peak hour, as written by the active-hours parser (8 -> "07:00 - 09:00")."""
    return f"{(hour - 1) % 24:02d}:00 - {(hour + 1) % 24:02d}:00"


def measured_optimal_schedule(profile: Mapping[str, Any]) -> MeasuredPostingHour | None:
    raw = profile.get("optimal_posting_hours_json")
    if not raw:
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        hour = int(data["peak_hour"])
        users = int(data.get("peak_users") or 0)
    except (TypeError, ValueError, KeyError, AttributeError):
        return None
    if users <= 0 or not 0 <= hour <= 23:
        return None
    window = data.get("peak_window")
    return MeasuredPostingHour(hour, window if isinstance(window, str) and window else peak_window(hour), users)
