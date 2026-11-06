"""Single source of truth for the network path ("egress") of a profile's account traffic.

Every HTTP client that talks to TikTok on behalf of a profile must call ``resolve_profile_egress``:
it returns the proxy URL to use, ``None`` only for a profile the user explicitly set to run from the
machine's own IP (``direct_connection``), and raises ``EgressBlocked`` otherwise. Never fall back to
a direct connection.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

SUPPORTED_PROTOCOLS = ("http", "https", "socks4", "socks5")


class EgressBlocked(PermissionError):
    """Account traffic refused: no usable proxy for this profile."""

    def __init__(self, message: str) -> None:
        super().__init__(f"AgentShield Strict Proxy Gate: {message}")


def normalize_protocol(protocol: Any) -> str | None:
    value = str(protocol or "http").strip().lower()
    if value == "socks5h":
        value = "socks5"
    if value == "socks4a":
        value = "socks4"
    return value if value in SUPPORTED_PROTOCOLS else None


def build_proxy_url(proxy: dict[str, Any] | None) -> str | None:
    """Proxy URL for HTTP clients (curl_cffi / requests), credentials URL-encoded.

    SOCKS5 becomes ``socks5h`` so hostnames are resolved by the proxy (no local DNS leak).
    """
    if not proxy or not proxy.get("host") or not proxy.get("port"):
        return None
    protocol = normalize_protocol(proxy.get("protocol"))
    if protocol is None:
        return None
    scheme = {"socks5": "socks5h", "socks4": "socks4a"}.get(protocol, protocol)
    user, password = proxy.get("username"), proxy.get("password")
    auth = ""
    if user:
        auth = quote(str(user), safe="")
        if password:
            auth += ":" + quote(str(password), safe="")
        auth += "@"
    return f"{scheme}://{auth}{proxy['host']}:{int(proxy['port'])}"


def redact_proxy_url(url: str | None) -> str:
    if not url:
        return "none"
    return re.sub(r"^([a-z0-9+.-]+://)[^@/]*@", r"\1***@", str(url), flags=re.IGNORECASE)


def resolve_profile_egress(profile: dict[str, Any] | None, proxy: dict[str, Any] | None) -> str | None:
    profile = profile or {}
    pid = profile.get("id", "?")
    if proxy:
        if proxy.get("status") == "leak_detected":
            raise EgressBlocked(f"Proxy #{proxy.get('id')} của hồ sơ #{pid} bị gắn cờ LEAK DETECTED: chặn request.")
        url = build_proxy_url(proxy)
        if not url:
            raise EgressBlocked(f"Proxy #{proxy.get('id')} của hồ sơ #{pid} không hợp lệ (thiếu host/port/giao thức).")
        return url
    if profile.get("vpn_config"):
        raise EgressBlocked(
            f"Hồ sơ #{pid} dùng WireGuard VPN: VPN chỉ áp dụng cho trình duyệt, request API cần một proxy."
        )
    if profile.get("direct_connection"):
        return None  # the user chose to run this profile from the machine's own IP
    raise EgressBlocked(f"Hồ sơ #{pid} chưa gán proxy: chặn request để bảo vệ IP máy thật.")
