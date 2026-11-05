"""Process-wide current entitlements, set by the license service after validation.

Every layer may ask `has(feature)` / `require(feature)`; nothing is unlocked without a valid license.
"""

from __future__ import annotations

import threading
import time

from src.domain.licensing.claims import LicenseClaims
from src.domain.licensing.plans import Feature, plan_features, upgrade_hint

_lock = threading.Lock()
_current: LicenseClaims | None = None


class LicenseFeatureError(PermissionError):
    def __init__(self, feature: Feature) -> None:
        super().__init__(upgrade_hint(feature))
        self.feature = feature


def set_current(claims: LicenseClaims | None) -> None:
    global _current
    with _lock:
        _current = claims


def current() -> LicenseClaims | None:
    with _lock:
        return _current


def has(feature: Feature) -> bool:
    claims = current()
    # Expiry is re-checked on every call so an app left open past the deadline loses access too.
    return claims is not None and claims.exp > time.time() and feature in plan_features(claims.plan)


def require(feature: Feature) -> None:
    if not has(feature):
        raise LicenseFeatureError(feature)
