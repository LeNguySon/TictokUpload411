"""
Unit & TDD Test Suite for WireGuard VPN Integration & Antidetect Hardening.
Tests:
1. WireGuard .conf parser, validator, and serialization.
2. Split DNS leak protection (--host-resolver-rules).
3. Auto GeoIP, Timezone & Language alignment injection into Default/Preferences.
4. Userspace VPN Bridge lifecycle per profile.
5. AssignProxyDialog WireGuard Tab 3 UI and database persistence.
"""

import json
from pathlib import Path

import pytest
from src.infrastructure.browser.orbita_launcher import OrbitaLauncher
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
from src.infrastructure.vpn.vpn_bridge import UserspaceVpnBridge
from src.infrastructure.vpn.wireguard_manager import WireGuardConfig
from src.presentation.dialogs.assign_proxy_dialog import AssignProxyDialog

SAMPLE_WG_CONF = """
[Interface]
PrivateKey = aaaaaabbbbbbccccccddddddeeeeeeffffffgggggg=
Address = 10.14.0.2/32
DNS = 1.1.1.1, 8.8.8.8

[Peer]
PublicKey = 1111112222223333334444445555556666667777778=
Endpoint = 198.51.100.25:51820
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
"""


@pytest.fixture
def env(tmp_path: Path):
    db_file = tmp_path / "test_vpn_app.db"
    run_all_migrations(db_file)
    profile_repo = ProfileRepository(db_file)
    proxy_repo = ProxyRepository(db_file)
    launcher = OrbitaLauncher(executable_path="C:/Program Files/Orbita/chrome.exe")
    return {
        "tmp_path": tmp_path,
        "db_file": db_file,
        "profile_repo": profile_repo,
        "proxy_repo": proxy_repo,
        "launcher": launcher,
    }


def test_wireguard_config_parser_and_serialization():
    cfg = WireGuardConfig.from_conf(SAMPLE_WG_CONF, name="us_vpn_node1")
    assert cfg.name == "us_vpn_node1"
    assert cfg.private_key == "aaaaaabbbbbbccccccddddddeeeeeeffffffgggggg="
    assert cfg.address == "10.14.0.2/32"
    assert "1.1.1.1" in (cfg.dns or "")
    assert cfg.peer_public_key == "1111112222223333334444445555556666667777778="
    assert cfg.endpoint == "198.51.100.25:51820"
    assert cfg.allowed_ips == "0.0.0.0/0"
    assert cfg.persistent_keepalive == 25

    # Test serialization round-trip
    conf_str = cfg.to_conf()
    assert "[Interface]" in conf_str
    assert "[Peer]" in conf_str
    assert "PrivateKey = aaaaaabbbbbbccccccddddddeeeeeeffffffgggggg=" in conf_str
    assert "Endpoint = 198.51.100.25:51820" in conf_str

    # Test dict round-trip
    d = cfg.to_dict()
    assert d["endpoint"] == "198.51.100.25:51820"
    reconstructed = WireGuardConfig.from_dict(d)
    assert reconstructed.endpoint == cfg.endpoint
    assert reconstructed.private_key == cfg.private_key


def test_antidetect_split_dns_leak_prevention_flag(env):
    launcher: OrbitaLauncher = env["launcher"]
    profile_dir = env["tmp_path"] / "prof_split_dns"

    args = launcher.build_launch_args(
        user_data_dir=profile_dir,
        proxy_uri="http://user:pass@185.48.54.7:5327",
    )

    # 1. Force all DNS through remote proxy, preventing local ISP / router DNS leak
    assert '--host-resolver-rules="MAP * 0.0.0.0 , EXCLUDE 185.48.54.7"' in args
    # 2. Enforce WebRTC IP permission check
    assert "--enforce-webrtc-ip-permission-check" in args


def test_timezone_and_geo_alignment_preferences_injection(env):
    launcher: OrbitaLauncher = env["launcher"]
    profile_dir = env["tmp_path"] / "prof_geo_sync"

    profile_data = {
        "id": 201,
        "name": "US_TikTok_Channel",
        "timezone_id": "America/Chicago",
        "latitude": 41.8781,
        "longitude": -87.6298,
        "country": "US",
    }
    proxy_data = {
        "host": "142.250.190.46",
        "port": 8080,
        "protocol": "http",
        "timezone": "America/Chicago",
        "country": "US",
    }

    launcher.prepare_profile_environment(profile_dir, profile_data, proxy_data)

    pref_path = profile_dir / "Default" / "Preferences"
    assert pref_path.exists()
    data = json.loads(pref_path.read_text(encoding="utf-8"))

    gologin = data["gologin"]
    # Timezone must match proxy location
    assert gologin["timezone"]["id"] == "America/Chicago"
    # Geolocation coordinates must match proxy location
    assert gologin["geoLocation"]["latitude"] == 41.8781
    assert gologin["geoLocation"]["longitude"] == -87.6298
    # Languages must match country
    assert "en-US" in gologin["languages"]


def test_userspace_vpn_bridge_lifecycle():
    cfg = WireGuardConfig.from_conf(SAMPLE_WG_CONF, name="test_bridge")
    bridge = UserspaceVpnBridge(profile_id=999, config=cfg, mock_mode=True)

    assert not bridge.is_running
    allocated_port = bridge.start()
    assert bridge.is_running
    assert allocated_port > 0
    assert bridge.local_port == allocated_port

    endpoint = bridge.get_proxy_endpoint()
    assert endpoint["protocol"] == "socks5"
    assert endpoint["host"] == "127.0.0.1"
    assert endpoint["port"] == allocated_port

    bridge.stop()
    assert not bridge.is_running


def test_assign_proxy_dialog_wireguard_tab_and_save(env, qapp):
    profile_repo: ProfileRepository = env["profile_repo"]
    proxy_repo: ProxyRepository = env["proxy_repo"]

    p_id = profile_repo.create({"name": "ProfileWithVPN"})

    dlg = AssignProxyDialog(
        profile_ids=[p_id],
        profile_repo=profile_repo,
        proxy_repo=proxy_repo,
    )

    # Verify Tab 3 exists: WireGuard VPN
    assert dlg.tabs.count() == 3
    assert "WireGuard" in dlg.tabs.tabText(2)

    # Switch to Tab 3
    dlg.tabs.setCurrentIndex(2)
    dlg.txt_wireguard.setPlainText(SAMPLE_WG_CONF)

    # Apply
    dlg._on_apply()

    updated = profile_repo.get_by_id(p_id)
    assert updated is not None
    vpn_conf = updated.get("vpn_config") or ""
    assert "PrivateKey" in vpn_conf
    assert "198.51.100.25:51820" in vpn_conf

    dlg.close()


def test_orbita_launcher_routes_through_wireguard_vpn(env, monkeypatch):
    launcher: OrbitaLauncher = env["launcher"]
    profile_dir = env["tmp_path"] / "prof_wg_route"

    profile_data = {
        "id": 888,
        "name": "ProfWithVPN",
        "storage_dir": str(profile_dir),
        "vpn_config": SAMPLE_WG_CONF,
    }

    # Mock subprocess.Popen so we don't actually spawn chrome.exe in unit test
    class DummyProc:
        pid = 12345

        def terminate(self):
            pass

    captured_args = []

    def fake_popen(args, shell=False):
        captured_args.extend(args)
        return DummyProc()

    import subprocess

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    proc = launcher.launch_profile(profile_data)
    assert proc.pid == 12345
    assert 888 in launcher.vpn_bridges
    bridge = launcher.vpn_bridges[888]
    assert bridge.is_running
    assert f"--proxy-server=socks5://127.0.0.1:{bridge.local_port}" in captured_args

    # Check Preferences proxy injection
    pref_path = profile_dir / "Default" / "Preferences"
    assert pref_path.exists()
    pref_data = json.loads(pref_path.read_text(encoding="utf-8"))
    assert pref_data["gologin"]["proxy"]["schema"] == "socks5"
    assert f"127.0.0.1:{bridge.local_port}" in pref_data["gologin"]["proxy"]["server"]

    # Now close profile
    closed = launcher.close_profile(888)
    assert closed
    assert not bridge.is_running
    assert 888 not in launcher.vpn_bridges
