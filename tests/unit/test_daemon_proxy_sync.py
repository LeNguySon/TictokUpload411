"""Second proxy audit (2026-11-06): the browser really uses the profile's proxy.

1. The SamMonny daemon rewrites Preferences from ITS OWN profile record at every start
   (gologin-launcher/profile_prep.rs). The app only told the daemon the proxy at creation time and
   later just edited Preferences, which the daemon overwrote: real data showed 6 profiles with a
   proxy in the app but "mode: none" in the daemon => SDK launches ran from the host IP.
2. A WireGuard profile launched through the SDK path had no VPN at all (the bridge only exists in
   the binary path).
3. build_launch_args split "user:p@ss@host" at the FIRST "@" => garbage --proxy-server.
4. ProfileRepository.update(proxy_id=...) did not end direct mode (edit dialog, round-robin assign).
5. Transfer import fell back to the SOURCE database's proxy id when a proxy failed to import.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from src.infrastructure.browser.daemon_proxy_sync import DaemonProxySyncError, sync_daemon_proxy
from src.infrastructure.browser.orbita_launcher import OrbitaLauncher
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository

PROXY = {"id": 3, "host": "198.51.100.4", "port": 1080, "protocol": "socks5", "username": "u", "password": "p@ss",
         "proxy_type": "static", "change_ip_url": None}


class FakeDaemon:
    """In-memory stand-in for the daemon's /api/v1 proxy + profile endpoints."""

    def __init__(self, pool=None, honour_assign=True):
        self.pool = list(pool or [])
        self.records: dict[str, dict] = {}
        self.calls: list[tuple] = []
        self.honour_assign = honour_assign

    def _request(self, method, path, payload=None, **_kw):
        self.calls.append((method, path, payload))
        if method == "GET" and path == "/api/v1/proxies":
            return list(self.pool)
        if method == "POST" and path == "/api/v1/proxies":
            new_id = 100 + len(self.pool)
            self.pool.append({**payload, "id": new_id})
            return {"status": "success", "id": new_id}
        if method == "POST" and path.endswith("/assign-proxy"):
            uuid = path.split("/")[4]
            px_id = payload["proxy_id"]
            item = next((p for p in self.pool if p["id"] == px_id), None)
            if self.honour_assign:
                self.records[uuid] = (
                    {"mode": item["protocol"], "host": item["host"], "port": item["port"],
                     "username": item.get("username"), "password": item.get("password")}
                    if item else {"mode": "none", "host": "", "port": 0}
                )
            return {"status": "success"}
        raise AssertionError((method, path))

    def get_profile(self, uuid):
        return MagicMock(proxy=self.records.get(uuid, {"mode": "none", "host": "", "port": 0}))


# ------------------------------------------------------------------ 1. daemon record sync
def test_sync_creates_pool_proxy_assigns_and_verifies():
    daemon = FakeDaemon()
    sync_daemon_proxy("uuid-1", PROXY, client=daemon)
    created = [c for c in daemon.calls if c[:2] == ("POST", "/api/v1/proxies")][0][2]
    assert created["protocol"] == "socks5" and created["port"] == 1080 and created["password"] == "p@ss"
    assert created["created_at"]  # required by the daemon's ProxyItem
    assert ("POST", "/api/v1/profiles/uuid-1/assign-proxy", {"proxy_id": 100}) in daemon.calls
    assert daemon.records["uuid-1"]["host"] == "198.51.100.4"


def test_sync_reuses_an_identical_pool_proxy():
    existing = {"id": 7, "host": "198.51.100.4", "port": 1080, "protocol": "socks5", "username": "u",
                "password": "p@ss"}
    daemon = FakeDaemon(pool=[existing])
    sync_daemon_proxy("uuid-1", PROXY, client=daemon)
    assert not [c for c in daemon.calls if c[:2] == ("POST", "/api/v1/proxies")]
    assert ("POST", "/api/v1/profiles/uuid-1/assign-proxy", {"proxy_id": 7}) in daemon.calls


def test_sync_direct_mode_clears_the_daemon_proxy():
    daemon = FakeDaemon()
    daemon.records["uuid-1"] = {"mode": "http", "host": "old", "port": 1}
    sync_daemon_proxy("uuid-1", None, client=daemon)
    assert ("POST", "/api/v1/profiles/uuid-1/assign-proxy", {"proxy_id": None}) in daemon.calls
    assert daemon.records["uuid-1"]["mode"] == "none"


def test_sync_fails_closed_when_the_daemon_record_does_not_match():
    with pytest.raises(DaemonProxySyncError):
        sync_daemon_proxy("uuid-1", PROXY, client=FakeDaemon(honour_assign=False))


def test_sdk_launch_syncs_the_daemon_record_before_start(tmp_path, monkeypatch):
    monkeypatch.setattr(OrbitaLauncher, "DAEMON_PROFILES_DIR", tmp_path)
    launcher = OrbitaLauncher(executable_path=tmp_path / "chrome.exe")
    order = []
    fake_gl = MagicMock()
    fake_gl.start.side_effect = lambda: order.append("start") or "127.0.0.1:9"
    with patch("src.infrastructure.browser.orbita_launcher.sync_daemon_proxy",
               side_effect=lambda uuid, proxy, **kw: order.append(("sync", uuid, proxy and proxy["host"]))), \
            patch("sammonny.gologin.gologin.GoLogin", return_value=fake_gl):
        launcher.launch_via_gologin_sdk(profile_id="uuid-1", proxy_data=PROXY)
        launcher.launch_via_gologin_sdk(profile_id="uuid-2", direct_connection=True)
    assert order == [("sync", "uuid-1", "198.51.100.4"), "start", ("sync", "uuid-2", None), "start"]


def test_sdk_launch_refuses_when_daemon_sync_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(OrbitaLauncher, "DAEMON_PROFILES_DIR", tmp_path)
    launcher = OrbitaLauncher(executable_path=tmp_path / "chrome.exe")
    fake_gl = MagicMock()
    with patch("src.infrastructure.browser.orbita_launcher.sync_daemon_proxy",
               side_effect=DaemonProxySyncError("mismatch")), \
            patch("sammonny.gologin.gologin.GoLogin", return_value=fake_gl), pytest.raises(DaemonProxySyncError):
        launcher.launch_via_gologin_sdk(profile_id="uuid-1", proxy_data=PROXY)
    fake_gl.start.assert_not_called()


# ------------------------------------------------------------------ 2. VPN profiles never use the SDK path
def test_sdk_launch_without_proxy_or_direct_opt_in_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(OrbitaLauncher, "DAEMON_PROFILES_DIR", tmp_path)
    launcher = OrbitaLauncher(executable_path=tmp_path / "chrome.exe")
    fake_gl = MagicMock()
    with patch("sammonny.gologin.gologin.GoLogin", return_value=fake_gl), pytest.raises(PermissionError):
        launcher.launch_via_gologin_sdk(profile_id="uuid-vpn")  # e.g. a WireGuard-only profile
    fake_gl.start.assert_not_called()


def test_upload_session_syncs_daemon_record(tmp_path):
    from src.infrastructure.tiktok.sammonny_adapter import _default_session_factory

    db = tmp_path / "s.db"
    run_all_migrations(db)
    px = ProxyRepository(db).import_line("1.2.3.4:8080:alice:pw")
    pid = ProfileRepository(db).create({"name": "S", "uuid": "uuid-up-1", "proxy_id": px})
    with patch("src.infrastructure.tiktok.sammonny_adapter.AntidetectEngine") as engine, patch(
        "src.infrastructure.tiktok.sammonny_adapter.sync_daemon_proxy"
    ) as sync:
        _default_session_factory(pid, db_path=db)
    assert sync.call_args.args[0] == "uuid-up-1" and sync.call_args.args[1]["host"] == "1.2.3.4"
    engine.assert_called_once()


# ------------------------------------------------------------------ 3. launch args with "@" in the password
def test_launch_args_keep_host_when_password_contains_at(tmp_path):
    launcher = OrbitaLauncher(executable_path=tmp_path / "chrome.exe")
    args = launcher.build_launch_args(tmp_path / "d", proxy_uri="http://user:p@ss@203.0.113.5:8080")
    assert "--proxy-server=http://203.0.113.5:8080" in args
    assert "--host-resolver-rules=MAP * 0.0.0.0 , EXCLUDE 203.0.113.5" in args


# ------------------------------------------------------------------ 4. update() ends direct mode
def test_update_with_a_proxy_ends_direct_mode(tmp_path):
    db = tmp_path / "u.db"
    run_all_migrations(db)
    repo = ProfileRepository(db)
    pid = repo.create({"name": "D", "uuid": "uuid-upd-1"})
    repo.set_direct_connection([pid])
    px = ProxyRepository(db).import_line("1.2.3.4:80")
    repo.update(pid, proxy_id=px)
    assert repo.get_by_id(pid)["direct_connection"] == 0


# ------------------------------------------------------------------ 5. transfer never reuses foreign ids
def test_transfer_import_never_assigns_the_source_proxy_id(tmp_path):
    import json
    import zipfile

    from src.presentation.dialogs.sync_transfer_dialog import import_project_dataset

    db = tmp_path / "t.db"
    run_all_migrations(db)
    profiles, proxies = ProfileRepository(db), ProxyRepository(db)
    unrelated = proxies.import_line("9.9.9.9:9999")  # same id as the source proxy, but a different proxy
    manifest = {
        "proxies": [{"id": unrelated}],  # unusable entry: fails to import
        "profiles": [{"name": "Moved", "proxy_id": unrelated}],
    }
    bundle = tmp_path / "b.zip"
    with zipfile.ZipFile(bundle, "w") as zf:
        zf.writestr("dataset_manifest.json", json.dumps(manifest))
    import_project_dataset(bundle, profiles, proxies)
    moved = next(p for p in profiles.list_all() if p["name"] == "Moved")
    assert moved["proxy_id"] is None
