"""Captures the live TikTok session of a running browser into the profile record.

TikTok refreshes the session cookie while the account is used; this stores the refreshed cookies
(``cookies_browser``) and their expiry so API features and the next launch use the current session.
The user's imported ``cookies_json`` is never overwritten.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.infrastructure.browser.cdp_session import fetch_tiktok_cookies, summarize_tiktok_cookies

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CaptureResult:
    ok: bool  # the browser answered
    logged_in: bool
    expires_at: float | None
    message: str


class CookieSessionService:
    def __init__(
        self,
        profile_repo: Any,
        signal_bus: Any = None,
        fetch: Callable[[str], list[dict[str, Any]]] = fetch_tiktok_cookies,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.profile_repo = profile_repo
        self.signal_bus = signal_bus
        self._fetch = fetch
        self._clock = clock

    def capture(self, profile_id: int, debugger_address: str) -> CaptureResult:
        try:
            cookies = self._fetch(debugger_address)
        except Exception as exc:
            logger.info("Session capture skipped for profile %s: %s", profile_id, exc)
            return CaptureResult(False, False, None, f"Không đọc được trình duyệt: {exc}")

        header, expires_at = summarize_tiktok_cookies(cookies, now=self._clock())
        if expires_at is None and "sessionid=" not in header:
            # Not logged in (or the page has not loaded yet): keep what is stored.
            return CaptureResult(True, False, None, "Trình duyệt chưa đăng nhập TikTok")

        updates: dict[str, Any] = {
            "cookies_browser": header,
            "session_expires_at": expires_at,
            "cookies_synced_at": datetime.fromtimestamp(self._clock()).isoformat(timespec="seconds"),
            "state_loggin_browser": 1,
            "status": "LIVE",
        }
        self.profile_repo.update(profile_id, **updates)
        if self.signal_bus is not None:
            try:
                public = {k: v for k, v in updates.items() if k != "cookies_browser"}
                self.signal_bus.profile_updated.emit(profile_id, public)
            except Exception as ignored:
                logger.debug("capture: ignored error: %s", ignored)
        return CaptureResult(True, True, expires_at, "Đã lưu phiên đăng nhập mới")
