"""
Avatar Cache Subsystem for TikTok Profiles.
Learned from Gloglin2609/engine/tiktok/avatar_cache.py.

Handles secure, asynchronous downloading and local caching of TikTok avatar images
to provide instant 60 FPS rendering in the GUI without remote CDN latency or token expiry.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.application.signals.app_signals import AppSignalBus
from src.infrastructure.database.connection import db_session

logger = logging.getLogger(__name__)

_DEFAULT_AVATAR_DIR = Path("data/avatars")


def get_avatar_cache_path(profile_id: int, storage_dir: str | Path | None = None) -> Path:
    """Returns the deterministic local destination path for a profile's avatar."""
    if storage_dir:
        s_path = Path(storage_dir)
        if s_path.exists() and s_path.is_dir():
            return s_path / "avatar.jpg"
    _DEFAULT_AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    return _DEFAULT_AVATAR_DIR / f"{profile_id}.jpg"


class _AvatarEgressBlocked(Exception):
    """The profile has no allowed route for the download (see resolve_profile_egress)."""


def _profile_egress(profile_id: int, db_path: Path | str | None) -> str | None:
    """Egress for the profile's avatar download, by the app's single egress rule (resolve_profile_egress):
    its proxy URL, or None when the user opted the profile into the machine's own IP (direct_connection).
    Raises _AvatarEgressBlocked when neither applies (no proxy, leaking proxy, VPN-only profile)."""
    from src.infrastructure.proxy.egress import EgressBlocked, resolve_profile_egress
    from src.infrastructure.tiktok.gologin_tiktok_client import GoLoginTikTokClient

    path = db_path or Path("data/app.db")
    with db_session(path, write=False) as conn:
        row = conn.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
    if not row:
        raise _AvatarEgressBlocked(f"profile {profile_id} not found")
    proxy = GoLoginTikTokClient(db_path=path).get_profile_proxy(profile_id)
    try:
        return resolve_profile_egress(dict(row), proxy)
    except EgressBlocked as blocked:
        raise _AvatarEgressBlocked(str(blocked)) from blocked


def _http_get(url: str, proxy_url: str | None, timeout: float) -> bytes | None:
    """GET through ``proxy_url``, or directly when it is None (profile opted into the machine's IP).
    curl_cffi when installed, else urllib with a ProxyHandler."""
    try:
        from curl_cffi import requests
        from curl_cffi.requests import ProxySpec

        proxies: ProxySpec | None = {"http": proxy_url, "https": proxy_url} if proxy_url else None
        resp = requests.get(url, impersonate="chrome123", timeout=timeout, proxies=proxies)
        return resp.content if resp.status_code == 200 and resp.content else None
    except ImportError:
        pass
    except Exception as e:
        logger.debug("Avatar download via curl_cffi failed: %s", e)
        return None

    if proxy_url and not proxy_url.startswith(("http://", "https://")):
        return None  # urllib cannot tunnel through SOCKS: never fall back to a direct connection
    import urllib.request

    handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url} if proxy_url else {})
    opener = urllib.request.build_opener(handler)
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/123.0.0.0 Safari/537.36"}
    )
    try:
        with opener.open(req, timeout=timeout) as response:
            status = getattr(response, "status", getattr(response, "code", 200))
            return response.read() if status == 200 else None
    except Exception as e:
        logger.debug("Avatar download via urllib proxy failed: %s", e)
        return None


def download_and_cache_avatar(
    profile_id: int,
    avatar_url: str,
    storage_dir: str | Path | None = None,
    db_path: Path | str | None = None,
    timeout: float = 10.0,
    signal_bus: AppSignalBus | None = None,
) -> str | None:
    """
    Downloads avatar image from URL, writes locally, and persists avatar_path in DB.
    Runs on background worker thread without blocking PyQt GUI MainThread.
    """
    if not avatar_url or not isinstance(avatar_url, str) or not avatar_url.startswith(("http://", "https://")):
        return None

    try:
        dest_path = get_avatar_cache_path(profile_id, storage_dir)
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        # Strict Proxy Gate: the profile's own proxy, or the machine's IP only if the user opted this profile
        # into it (direct_connection). Never an implicit direct download: it links every account to one IP.
        try:
            proxy_url = _profile_egress(profile_id, db_path)
        except _AvatarEgressBlocked as blocked:
            logger.warning("Avatar download skipped for profile %s: %s", profile_id, blocked)
            return None
        content = _http_get(avatar_url, proxy_url, timeout)

        if not content or len(content) < 50:
            logger.warning("Downloaded avatar content is empty or too small for profile %s", profile_id)
            return None

        # Write atomically
        tmp_path = dest_path.with_suffix(".tmp")
        tmp_path.write_bytes(content)
        tmp_path.replace(dest_path)

        path_str = str(dest_path.resolve())

        # Update SQLite database
        actual_db = db_path or Path("data/app.db")
        with db_session(actual_db) as conn:
            conn.execute(
                "UPDATE profiles SET avatar_path = ?, avatar_url = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?;",
                (path_str, avatar_url, profile_id),
            )

        bus = signal_bus or AppSignalBus.instance()
        if bus:
            bus.profile_updated.emit(profile_id, {"avatar_path": path_str, "avatar_url": avatar_url})

        logger.info("Successfully cached avatar for profile %s to %s", profile_id, path_str)
        return path_str

    except Exception as exc:
        logger.error("Failed to download and cache avatar for profile %s: %s", profile_id, exc)
        return None
