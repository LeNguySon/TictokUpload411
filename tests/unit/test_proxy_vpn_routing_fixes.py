"""Proxy / VPN audit of 2026-11-07 (live routing proof with two logging proxies on a copy of the real DB):

1. every deep sync and every "Quét Toàn Kênh" scanned all videos for penalties TWICE (fetch_account_standing scans
   them itself, then the caller scanned again): 162 of the 177 requests of a sync went through the proxy;
2. a profile could hold a proxy AND a WireGuard VPN: the table showed "WireGuard VPN" while the browser and the API
   used the proxy; assigning one must replace the other;
3. one proxy assigned to many profiles (27 accounts on one IP in the real DB) is silent: the dialog must say so.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository

WG = "[Interface]\nPrivateKey = x\n[Peer]\nPublicKey = y\nEndpoint = 1.2.3.4:51820\n"


@pytest.fixture
def repos(tmp_path: Path):
    db = tmp_path / "app.db"
    run_all_migrations(db)
    return ProfileRepository(db), ProxyRepository(db), db


# --- 1. penalty scan once -------------------------------------------------------------------------------------


def _moderation(db):
    from src.infrastructure.tiktok.moderation_service import TikTokModerationService

    return TikTokModerationService(db_path=db)


def test_full_channel_scan_checks_penalties_once(repos):
    profiles, _, db = repos
    pid = profiles.create({"name": "ch", "cookies_json": "sessionid=x"})
    mod = _moderation(db)
    with patch.object(mod, "fetch_video_violations", return_value=[{"video_id": "1"}]) as scan, \
            patch.object(mod, "_request_tiktok_api", return_value={}):
        res = mod.scan_full_channel_health(pid)
    assert scan.call_count == 1
    assert res["standing"]["strike_count"] == 1


def test_deep_sync_checks_penalties_once(repos):
    from src.infrastructure.tiktok.moderation_service import TikTokModerationService
    from src.infrastructure.tiktok.passive_sync_service import PassiveTikTokSyncService

    profiles, proxies, db = repos
    pid = profiles.create({"name": "ch", "cookies_json": "sessionid=x", "direct_connection": 1})
    svc = PassiveTikTokSyncService(profiles, proxies, db_path=db)
    with patch.object(svc.client, "get_profile_cookie_header", return_value="sessionid=x"), \
            patch.object(svc.client, "request_api", return_value={}), \
            patch.object(TikTokModerationService, "fetch_video_violations", return_value=[]) as scan, \
            patch.object(TikTokModerationService, "_request_tiktok_api", return_value={}), \
            patch("src.infrastructure.tiktok.passive_sync_service.download_and_cache_avatar"):
        svc.sync_profile_deep_creator_api(pid)
    assert scan.call_count == 1


def test_account_standing_alone_still_scans(repos):
    profiles, _, db = repos
    pid = profiles.create({"name": "ch", "cookies_json": "sessionid=x"})
    mod = _moderation(db)
    with patch.object(mod, "fetch_video_violations", return_value=[]) as scan, \
            patch.object(mod, "_request_tiktok_api", return_value={}):
        mod.fetch_account_standing(pid)
    assert scan.call_count == 1


# --- 2. proxy and VPN are exclusive -----------------------------------------------------------------------------


def test_assigning_a_vpn_replaces_the_proxy(repos):
    profiles, proxies, _ = repos
    px = proxies.create(host="10.0.0.1", port=8080)
    pid = profiles.create({"name": "a", "proxy_id": px})
    profiles.update(pid, vpn_config=WG)
    row = profiles.get_by_id(pid)
    assert row["vpn_config"] and row["proxy_id"] is None


def test_assigning_a_proxy_replaces_the_vpn(repos):
    profiles, proxies, _ = repos
    px = proxies.create(host="10.0.0.1", port=8080)
    a = profiles.create({"name": "a", "vpn_config": WG})
    b = profiles.create({"name": "b", "vpn_config": WG})
    c = profiles.create({"name": "c", "vpn_config": WG})
    profiles.update(a, proxy_id=px)
    profiles.bulk_assign_proxy([b], px)
    profiles.bulk_update_fields([c], {"proxy_id": px})
    for pid in (a, b, c):
        row = profiles.get_by_id(pid)
        assert row["proxy_id"] == px and not row["vpn_config"], pid


def test_existing_profiles_with_both_keep_what_the_browser_used(repos):
    """Migration: the browser used the proxy when both were set, so the proxy stays and the VPN is cleared."""
    profiles, proxies, db = repos
    px = proxies.create(host="10.0.0.1", port=8080)
    pid = profiles.create({"name": "a"})
    import sqlite3

    conn = sqlite3.connect(db)
    conn.execute("UPDATE profiles SET proxy_id=?, vpn_config=? WHERE id=?", (px, WG, pid))
    conn.commit()
    conn.close()
    run_all_migrations(db)
    row = profiles.get_by_id(pid)
    assert row["proxy_id"] == px and not row["vpn_config"]


# --- 3. shared proxy warning ------------------------------------------------------------------------------------


def test_proxy_usage_counts_and_sharing_warning(repos):
    from src.presentation.dialogs.assign_proxy_dialog import shared_proxy_warning

    profiles, proxies, _ = repos
    px1 = proxies.create(host="10.0.0.1", port=8080)
    px2 = proxies.create(host="10.0.0.2", port=8080)
    others = [profiles.create({"name": f"o{i}", "proxy_id": px1}) for i in range(3)]
    usage = profiles.proxy_usage_counts()
    assert usage == {px1: 3}

    # 2 selected profiles on px2 (unused): they share one IP between themselves
    assert "2 hồ sơ" in shared_proxy_warning(usage, {px2: 2}, proxies)
    # 1 selected profile on px1, already used by 3 others
    assert "4 hồ sơ" in shared_proxy_warning(usage, {px1: 1}, proxies)
    # one proxy per profile: no warning
    assert shared_proxy_warning(usage, {px2: 1}, proxies) == ""
    # a selected profile that already had px1 is not counted twice
    assert "3 hồ sơ" in shared_proxy_warning(usage, {px1: 1}, proxies, already_on={px1: 1})
    assert others


def test_proxy_combo_shows_how_many_profiles_use_each_proxy(repos, qtbot):
    from src.presentation.dialogs.assign_proxy_dialog import AssignProxyDialog

    profiles, proxies, _ = repos
    px1 = proxies.create(host="10.0.0.1", port=8080)
    for i in range(2):
        profiles.create({"name": f"o{i}", "proxy_id": px1})
    target = profiles.create({"name": "t"})
    dlg = AssignProxyDialog(profile_ids=[target], profile_repo=profiles, proxy_repo=proxies)
    qtbot.addWidget(dlg)
    texts = [dlg.combo_proxy.itemText(i) for i in range(dlg.combo_proxy.count())]
    assert any("10.0.0.1" in t and "2 hồ sơ đang dùng" in t for t in texts)
