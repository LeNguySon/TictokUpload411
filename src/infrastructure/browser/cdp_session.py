"""Minimal Chrome DevTools Protocol access to a running (SDK-launched) browser.

Reading cookies through DevTools returns them decrypted with their real expiry, which the cookie
SQLite file cannot give once Chrome/Orbita has re-encrypted the values it writes.
"""

from __future__ import annotations

import json
import time
import urllib.request
from typing import Any

SESSION_COOKIES = ("sessionid", "sessionid_ss", "sid_tt")


class CdpError(RuntimeError):
    pass


def _http_base(debugger_address: str) -> str:
    addr = str(debugger_address).strip()
    for prefix in ("http://", "https://", "ws://", "wss://"):
        if addr.startswith(prefix):
            addr = addr[len(prefix) :]
    return "http://" + addr.split("/", 1)[0]


def cdp_call(debugger_address: str, method: str, params: dict[str, Any] | None = None, timeout: float = 10) -> dict:
    """One browser-level DevTools command; returns its ``result``."""
    from websockets.sync.client import connect

    with urllib.request.urlopen(f"{_http_base(debugger_address)}/json/version", timeout=timeout) as resp:
        ws_url = json.load(resp)["webSocketDebuggerUrl"]
    with connect(ws_url, open_timeout=timeout, close_timeout=2, max_size=None) as ws:
        ws.send(json.dumps({"id": 1, "method": method, "params": params or {}}))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            msg = json.loads(ws.recv(timeout=max(0.1, deadline - time.monotonic())))
            if msg.get("id") == 1:
                if "error" in msg:
                    raise CdpError(str(msg["error"].get("message") or msg["error"]))
                return dict(msg.get("result") or {})
    raise CdpError(f"No DevTools reply to {method}")


def fetch_tiktok_cookies(debugger_address: str) -> list[dict[str, Any]]:
    cookies = cdp_call(debugger_address, "Storage.getCookies").get("cookies") or []
    return [c for c in cookies if str(c.get("domain", "")).lstrip(".").endswith("tiktok.com")]


def open_url(debugger_address: str, url: str) -> None:
    cdp_call(debugger_address, "Target.createTarget", {"url": url})


def summarize_tiktok_cookies(cookies: list[dict[str, Any]], now: float | None = None) -> tuple[str, float | None]:
    """("name=value; ..." of the live TikTok cookies, expiry of the session cookie or None if logged out)."""
    now = time.time() if now is None else now
    pairs: dict[str, str] = {}
    session_expiry: float | None = None
    for c in cookies:
        if not str(c.get("domain", "")).lstrip(".").endswith("tiktok.com") or not c.get("name"):
            continue
        expires = float(c.get("expires", -1) or -1)
        if 0 < expires <= now:
            continue  # already expired
        pairs.setdefault(str(c["name"]), str(c.get("value", "")))
        if c["name"] in SESSION_COOKIES and expires > 0:
            session_expiry = max(session_expiry or 0.0, expires)
    if not any(name in pairs for name in SESSION_COOKIES):
        session_expiry = None
    return "; ".join(f"{k}={v}" for k, v in pairs.items()), session_expiry
