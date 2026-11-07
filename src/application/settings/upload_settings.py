"""User-selectable upload method and related options (persisted in the app's QSettings)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class UploadMethod(StrEnum):
    AUTO = "auto"  # official API when the profile has an OAuth token, otherwise the Studio page
    OFFICIAL = "official"  # TikTok Content Posting API (Direct Post, OAuth)
    HYBRID = "hybrid"  # cookie API in the profile's browser (TOS upload + signed publish request)
    STUDIO = "studio"  # TikTok Studio web page automation (DOM)


METHOD_LABELS: dict[UploadMethod, str] = {
    UploadMethod.AUTO: "Tự động (khuyến nghị)",
    UploadMethod.OFFICIAL: "API chính thức (OAuth Direct Post)",
    UploadMethod.HYBRID: "Cookie API (Hybrid) — chưa hoạt động",
    UploadMethod.STUDIO: "Trình duyệt TikTok Studio (DOM)",
}


@dataclass(frozen=True)
class UploadSettings:
    method: UploadMethod = UploadMethod.AUTO
    allow_fallback: bool = False  # switch to another method when the chosen one fails (risk of duplicates)
    studio_show_browser: bool = False  # DOM/Hybrid: visible browser window instead of headless
    reconcile_official: bool = True  # poll TikTok until an official upload is really published


_PREFIX = "upload/"


def load_upload_settings(store: Any) -> UploadSettings:
    raw = str(store.value(_PREFIX + "method", UploadMethod.AUTO.value) or UploadMethod.AUTO.value)
    try:
        method = UploadMethod(raw)
    except ValueError:
        method = UploadMethod.AUTO
    return UploadSettings(
        method=method,
        allow_fallback=bool(store.value(_PREFIX + "allow_fallback", False, type=bool)),
        studio_show_browser=bool(store.value(_PREFIX + "studio_show_browser", False, type=bool)),
        reconcile_official=bool(store.value(_PREFIX + "reconcile_official", True, type=bool)),
    )


def save_upload_settings(settings: UploadSettings, store: Any) -> None:
    store.setValue(_PREFIX + "method", settings.method.value)
    store.setValue(_PREFIX + "allow_fallback", bool(settings.allow_fallback))
    store.setValue(_PREFIX + "studio_show_browser", bool(settings.studio_show_browser))
    store.setValue(_PREFIX + "reconcile_official", bool(settings.reconcile_official))
    store.sync()
