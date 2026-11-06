"""Make the SamMonny daemon's OWN profile record use the app's proxy before a browser starts.

The daemon rewrites Default/Preferences from its profile record on every start
(gologin-launcher/profile_prep.rs): editing Preferences alone is overwritten, and a record left at
"mode: none" makes the browser run from the machine's own IP. The record is changed through the
daemon API (proxy pool + /profiles/{id}/assign-proxy) and read back; any mismatch raises, so the
caller never starts that browser.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from src.infrastructure.proxy.egress import normalize_protocol

logger = logging.getLogger(__name__)


class DaemonProxySyncError(RuntimeError):
    pass


def _default_client() -> Any:
    from sammonny.core.client import SamMonnyDaemonClient

    return SamMonnyDaemonClient()


def _norm_user(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def _record_proxy(client: Any, profile_uuid: str) -> dict[str, Any]:
    proxy = getattr(client.get_profile(profile_uuid), "proxy", None)
    if isinstance(proxy, dict):
        return proxy
    return {"mode": "none", "host": "", "port": 0}


def _pool_proxy_id(client: Any, proxy: dict[str, Any], mode: str) -> int:
    host, port = str(proxy["host"]), int(proxy["port"])
    user, password = _norm_user(proxy.get("username")), _norm_user(proxy.get("password"))
    for item in client._request("GET", "/api/v1/proxies") or []:
        if (
            str(item.get("host")) == host
            and int(item.get("port") or 0) == port
            and _norm_user(item.get("username")) == user
            and _norm_user(item.get("password")) == password
            and str(item.get("protocol", "")).lower() == mode
            and item.get("id") is not None
        ):
            return int(item["id"])
    created = client._request(
        "POST",
        "/api/v1/proxies",
        {
            "host": host,
            "port": port,
            "username": user,
            "password": password,
            "protocol": mode,
            "proxy_type": str(proxy.get("proxy_type") or "static"),
            "change_ip_url": proxy.get("change_ip_url"),
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        },
    )
    new_id = (created or {}).get("id")
    if new_id is None:
        raise DaemonProxySyncError("Daemon did not return an id for the new proxy")
    return int(new_id)


def sync_daemon_proxy(profile_uuid: str, proxy: dict[str, Any] | None, client: Any = None) -> None:
    """Sets the daemon record of ``profile_uuid`` to ``proxy`` (None = no proxy) and verifies it."""
    client = client or _default_client()
    if proxy:
        mode = normalize_protocol(proxy.get("protocol"))
        if mode is None or not proxy.get("host") or not proxy.get("port"):
            raise DaemonProxySyncError(f"Proxy #{proxy.get('id')} is not usable by the daemon")
        daemon_proxy_id: int | None = _pool_proxy_id(client, proxy, mode)
    else:
        mode, daemon_proxy_id = "none", None

    client._request("POST", f"/api/v1/profiles/{profile_uuid}/assign-proxy", {"proxy_id": daemon_proxy_id})

    record = _record_proxy(client, profile_uuid)
    record_mode = str(record.get("mode") or "none").lower()
    if proxy:
        ok = (
            record_mode == mode
            and str(record.get("host")) == str(proxy["host"])
            and int(record.get("port") or 0) == int(proxy["port"])
        )
    else:
        ok = record_mode == "none" or not record.get("host")
    if not ok:
        raise DaemonProxySyncError(
            f"Daemon profile {profile_uuid} still has proxy {record_mode}://{record.get('host')}:{record.get('port')}"
        )
    logger.info("Daemon profile %s proxy set to %s", profile_uuid,
                f"{mode}://{proxy['host']}:{proxy['port']}" if proxy else "none (direct)")
