"""Which stored cookie represents a profile's current TikTok session.

``cookies_browser`` is read from the browser (the session TikTok refreshed), ``cookies_json`` is what the
user imported. A new import clears ``cookies_browser`` (ProfileRepository), so the browser copy is always
at least as recent as the import.
"""

from __future__ import annotations

from typing import Any


def pick_session_cookie(profile: dict[str, Any] | None) -> str:
    if not profile:
        return ""
    return str(profile.get("cookies_browser") or profile.get("cookies_json") or profile.get("cookie") or "")
