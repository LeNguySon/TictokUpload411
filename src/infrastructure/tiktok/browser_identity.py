"""
The browser identity every app request presents for a profile.

The profile's real browser (Orbita, started by the daemon with the profile's fixed fingerprint) is e.g. Chrome/139 on
Windows with vi-VN languages. Requests the app sends itself (Creator API, avatar, DOM pages) must present the SAME
browser: same User-Agent, client hints (sec-ch-ua*) and Accept-Language, and the TLS/HTTP2 fingerprint of the closest
Chrome curl_cffi can impersonate. They used to mix Chrome 120/123/152 and en-US, and curl_cffi added
``sec-ch-ua-platform: "macOS"`` to a Windows User-Agent.
"""

from __future__ import annotations

import re
from typing import Any

from src.domain.fingerprint.browser_fingerprint import fingerprint_of

DEFAULT_IMPERSONATE = "chrome136"
_PLATFORM_HINT = {"win32": "Windows", "win64": "Windows", "macintel": "macOS", "linux x86_64": "Linux"}


def chrome_major(user_agent: str | None) -> int | None:
    match = re.search(r"Chrome/(\d+)", user_agent or "")
    return int(match.group(1)) if match else None


def _desktop_chrome_targets() -> list[int]:
    try:
        from curl_cffi.requests import BrowserType

        names = [b.value for b in BrowserType]
    except Exception:  # pragma: no cover - curl_cffi ships with the app
        names = [DEFAULT_IMPERSONATE]
    majors = []
    for name in names:
        m = re.fullmatch(r"chrome(\d+)", name)  # desktop only (no _android / _macos / "a" variants)
        if m:
            majors.append(int(m.group(1)))
    return sorted(majors)


def impersonate_target(user_agent: str | None) -> str:
    """curl_cffi target for the TLS/HTTP2 fingerprint: the newest desktop Chrome not newer than the User-Agent
    (the oldest available one for older agents)."""
    major = chrome_major(user_agent)
    targets = _desktop_chrome_targets()
    if major is None or not targets:
        return DEFAULT_IMPERSONATE
    not_newer = [t for t in targets if t <= major]
    return f"chrome{max(not_newer) if not_newer else targets[0]}"


def accept_language(languages: list[str] | None) -> str:
    """Chrome's Accept-Language for a navigator.languages list (q decreasing by 0.1)."""
    langs = [str(x) for x in (languages or []) if x] or ["en-US", "en"]
    parts = [langs[0]] + [f"{lang};q={max(0.1, 1 - 0.1 * i):.1f}" for i, lang in enumerate(langs[1:], start=1)]
    return ",".join(parts)


def request_identity(profile: dict[str, Any]) -> tuple[dict[str, str], str]:
    """Headers (User-Agent, Accept-Language, sec-ch-ua*) and curl_cffi impersonate target for ``profile``."""
    fp = fingerprint_of(profile)
    nav = fp.get("navigator") or {}
    user_agent = str(nav.get("user_agent") or profile.get("user_agent") or "")
    major = chrome_major(user_agent) or int(DEFAULT_IMPERSONATE.removeprefix("chrome"))
    platform = _PLATFORM_HINT.get(str(nav.get("platform") or "Win32").lower(), "Windows")
    headers = {
        "User-Agent": user_agent,
        "Accept-Language": accept_language(nav.get("languages")),
        "sec-ch-ua": f'"Not;A=Brand";v="99", "Google Chrome";v="{major}", "Chromium";v="{major}"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": f'"{platform}"',
    }
    return headers, impersonate_target(user_agent)
