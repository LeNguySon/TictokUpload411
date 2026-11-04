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

        content: bytes | None = None
        try:
            from curl_cffi import requests

            resp = requests.get(avatar_url, impersonate="chrome123", timeout=timeout)
            if resp.status_code == 200 and resp.content:
                content = resp.content
        except Exception:
            pass

        if not content:
            import urllib.request

            req = urllib.request.Request(
                avatar_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/123.0.0.0 Safari/537.36"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                status = getattr(response, "status", getattr(response, "code", 200))
                if status == 200:
                    content = response.read()

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
