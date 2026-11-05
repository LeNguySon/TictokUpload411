"""Data-collection audit (offline; no TikTok calls).

1. Offline browser-cookie check overwrote `cookies_json` (the user's imported cookies) with whatever
   it read from the Chromium DB, as a JSON dict (format everything else parses as a header string).
   Chrome/Orbita store cookie values encrypted (`value` is empty), so a logged-in profile read as
   "no sessionid" -> marked DIE and its imported cookies wiped.
2. The sniffer overwrote the user's profile `name` with the TikTok uniqueId.
3. TikTokModerationService wrote with a bare sqlite3.connect (no busy_timeout / WAL settings).
4. Avatars were downloaded straight from the host IP, bypassing the profile proxy (Strict Proxy Gate).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository

FAR_FUTURE = 13_500_000_000_000_000  # Chromium microseconds (~2028)
IMPORTED = "msToken=abc123; tt_csrf_token=zzz"


@pytest.fixture
def env(tmp_path: Path):
    db = tmp_path / "dc.db"
    run_all_migrations(db)
    profiles, proxies = ProfileRepository(db), ProxyRepository(db)
    storage = tmp_path / "profiles" / "p1"
    pid = profiles.create({"name": "Kênh JP 01", "uuid": "uuid-dc-0001", "storage_dir": str(storage), "status": "LIVE"})
    profiles.update(pid, cookies_json=IMPORTED)
    return {"db": db, "profiles": profiles, "proxies": proxies, "pid": pid, "storage": storage}


def _cookie_db(storage: Path, rows: list[tuple[str, str, bytes]]) -> None:
    path = storage / "Default" / "Network" / "Cookies"
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as c:
        c.execute(
            "CREATE TABLE cookies (host_key TEXT, name TEXT, value TEXT, expires_utc INTEGER, encrypted_value BLOB)"
        )
        c.executemany(
            "INSERT INTO cookies VALUES ('.tiktok.com', ?, ?, ?, ?)", [(n, v, FAR_FUTURE, e) for n, v, e in rows]
        )


def _service(env):
    from src.infrastructure.tiktok.passive_sync_service import PassiveTikTokSyncService

    return PassiveTikTokSyncService(
        env["profiles"],
        env["proxies"],
        sniffer=MagicMock(),
        client=MagicMock(),
        signal_bus=MagicMock(),
        db_path=env["db"],
    )


def test_offline_cookie_sync_never_overwrites_imported_cookies(env):
    _cookie_db(env["storage"], [("sessionid", "SESS1", b""), ("msToken", "TOK", b"")])
    res = _service(env).sync_profile_offline_cookies(env["pid"])
    row = env["profiles"].get_by_id(env["pid"])
    assert res["is_live"] is True
    assert row["cookies_json"] == IMPORTED, "imported cookies must be kept"
    assert "sessionid=SESS1" in row["cookies_browser"], "browser cookies go to cookies_browser as a header string"
    assert not row["cookies_browser"].lstrip().startswith("{")
    assert row["status"] == "LIVE"


def test_encrypted_browser_cookies_do_not_mark_profile_die(env):
    _cookie_db(env["storage"], [("sessionid", "", b"v10\x01\x02encrypted"), ("msToken", "", b"v10\x03")])
    res = _service(env).sync_profile_offline_cookies(env["pid"])
    row = env["profiles"].get_by_id(env["pid"])
    assert res["ok"] is False, "encrypted values cannot be judged offline"
    assert row["status"] == "LIVE" and row["cookies_json"] == IMPORTED and not row["cookies_browser"]


def test_readable_cookies_without_session_mark_die_but_keep_imports(env):
    _cookie_db(env["storage"], [("msToken", "TOK", b""), ("ttwid", "W", b"")])
    _service(env).sync_profile_offline_cookies(env["pid"])
    row = env["profiles"].get_by_id(env["pid"])
    assert row["status"] == "DIE"
    assert row["cookies_json"] == IMPORTED


def test_sniffer_keeps_user_profile_name(env):
    from src.infrastructure.tiktok.network_sniffer import TikTokNetworkSniffer

    sniffer = TikTokNetworkSniffer(db_path=env["db"], signal_bus=MagicMock())
    payload = {"userInfo": {"user": {"uniqueId": "tiktok.handle", "nickname": "Nick"}, "stats": {"followerCount": 10}}}
    sniffer.process_api_response(env["pid"], "https://www.tiktok.com/api/user/detail/?uniqueId=x", payload)
    row = env["profiles"].get_by_id(env["pid"])
    assert row["name"] == "Kênh JP 01"
    assert row["username_on_tiktok"] == "tiktok.handle"


def test_sniffer_fills_auto_generated_profile_name(env):
    from src.infrastructure.tiktok.network_sniffer import TikTokNetworkSniffer

    auto_id = env["profiles"].create({"uuid": "uuid-dc-auto-0001"})  # repository default name "Profile_xxxxxxxx"
    sniffer = TikTokNetworkSniffer(db_path=env["db"], signal_bus=MagicMock())
    payload = {"userInfo": {"user": {"uniqueId": "real.handle"}}}
    sniffer.process_api_response(auto_id, "https://www.tiktok.com/api/user/detail/?uniqueId=x", payload)
    assert env["profiles"].get_by_id(auto_id)["name"] == "real.handle"


def test_moderation_service_uses_configured_connection(env):
    from src.infrastructure.tiktok.moderation_service import TikTokModerationService

    conn = TikTokModerationService(db_path=env["db"])._get_connection()
    try:
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] >= 10000
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        conn.close()


def test_avatar_download_is_blocked_without_proxy(env):
    from src.infrastructure.tiktok import avatar_cache_service as mod

    with patch.object(mod, "_http_get", side_effect=AssertionError("direct download from host IP")):
        assert mod.download_and_cache_avatar(env["pid"], "https://p16.tiktokcdn.com/a.jpg", db_path=env["db"]) is None


def test_avatar_download_goes_through_profile_proxy(env):
    from src.infrastructure.tiktok import avatar_cache_service as mod

    px = env["proxies"].create(host="10.1.2.3", port=8080, username="u", password="p")
    env["profiles"].update(env["pid"], proxy_id=px)
    with patch.object(mod, "_http_get", return_value=b"PNG-AVATAR" + b"0" * 100) as get:
        path = mod.download_and_cache_avatar(
            env["pid"], "https://p16.tiktokcdn.com/a.jpg", storage_dir=env["storage"], db_path=env["db"]
        )
    assert path
    assert get.call_args.args[1].endswith("@10.1.2.3:8080")


def test_avatar_download_refuses_leaking_proxy(env):
    from src.infrastructure.tiktok import avatar_cache_service as mod

    px = env["proxies"].create(host="10.9.9.9", port=8080)
    env["proxies"].update(px, status="leak_detected")
    env["profiles"].update(env["pid"], proxy_id=px)
    with patch.object(mod, "_http_get", side_effect=AssertionError("leaking proxy used")):
        assert mod.download_and_cache_avatar(env["pid"], "https://p16.tiktokcdn.com/a.jpg", db_path=env["db"]) is None
