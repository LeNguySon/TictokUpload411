"""Commercial plans and the features each one unlocks (plans are cumulative)."""

from __future__ import annotations

from enum import StrEnum


class Feature(StrEnum):
    PROFILES = "profiles"  # profiles, proxies, browsers
    UPLOAD = "upload"  # video import, scheduling, automatic upload
    CHANNEL_HEALTH = "channel_health"  # strikes check, channel health/radar, appeals


class Plan(StrEnum):
    PROFILE = "profile"
    UPLOAD = "upload"
    PRO = "pro"


_PLAN_FEATURES: dict[Plan, frozenset[Feature]] = {
    Plan.PROFILE: frozenset({Feature.PROFILES}),
    Plan.UPLOAD: frozenset({Feature.PROFILES, Feature.UPLOAD}),
    Plan.PRO: frozenset({Feature.PROFILES, Feature.UPLOAD, Feature.CHANNEL_HEALTH}),
}

PLAN_DISPLAY_NAMES: dict[Plan, str] = {
    Plan.PROFILE: "Gói 1 - Hồ sơ",
    Plan.UPLOAD: "Gói 2 - Hồ sơ + Upload",
    Plan.PRO: "Gói 3 - Toàn diện",
}

# Cheapest plan that unlocks a feature (for "upgrade required" messages).
FEATURE_MIN_PLAN: dict[Feature, Plan] = {
    Feature.PROFILES: Plan.PROFILE,
    Feature.UPLOAD: Plan.UPLOAD,
    Feature.CHANNEL_HEALTH: Plan.PRO,
}


def plan_features(plan: Plan) -> set[Feature]:
    return set(_PLAN_FEATURES[plan])


def upgrade_hint(feature: Feature) -> str:
    return f"Tính năng này cần {PLAN_DISPLAY_NAMES[FEATURE_MIN_PLAN[feature]]} trở lên."
