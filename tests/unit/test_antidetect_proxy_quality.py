"""
Comprehensive Unit & Quality Assurance Test Suite for Orbita Antidetect & Real Proxy Handling.
Enforces ANTIDETECT_MASTER_SPEC compliance:
1. WebRTC & IPv6 leak prevention.
2. Authenticated proxy injection via Default/Preferences JSON without CLI credential leakage.
3. Anti-bot stealth parameters (--disable-blink-features=AutomationControlled,WebGPU).
4. Strict argument ordering (--user-data-dir as the terminal parameter).
5. Pre-launch lock sanitization.
6. Network leak audit integration.
"""

import json
from pathlib import Path

import pytest
from src.application.services.proxy_service import ProxyService
from src.domain.fingerprint.browser_fingerprint import generate_fingerprint
from src.domain.policies.network_leak_policy import NetworkLeakPolicy
from src.infrastructure.browser.orbita_launcher import OrbitaLauncher
from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository


@pytest.fixture
def temp_env(tmp_path: Path):
    db_file = tmp_path / "test_app.db"
    run_all_migrations(db_file)
    proxy_repo = ProxyRepository(db_file)
    leak_policy = NetworkLeakPolicy(known_host_ips={"192.168.1.100", "127.0.0.1"})
    proxy_service = ProxyService(proxy_repo, leak_policy)
    launcher = OrbitaLauncher(executable_path="C:/Program Files/Orbita/chrome.exe")
    return {
        "tmp_path": tmp_path,
        "db_file": db_file,
        "proxy_repo": proxy_repo,
        "proxy_service": proxy_service,
        "launcher": launcher,
    }


def test_webrtc_and_ipv6_leak_prevention_flags(temp_env):
    launcher: OrbitaLauncher = temp_env["launcher"]
    profile_dir = temp_env["tmp_path"] / "prof_webrtc"

    args = launcher.build_launch_args(
        user_data_dir=profile_dir,
        proxy_uri="http://103.20.5.10:8080",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/152.0.0.0",
    )

    # 1. WebRTC non-proxied UDP must be disabled to prevent IP leaks
    assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" in args
    # 2. IPv6 must be disabled to prevent dual-stack DNS/IPv6 leaks
    assert "--disable-ipv6" in args
    # 3. Encryption must be disabled for raw cookie storage access
    assert "--disable-encryption" in args
    # 4. Font masking mode must be enabled
    assert "--font-masking-mode=1" in args
    # 5. Anti-bot flags suppressing AutomationControlled
    assert "--disable-blink-features=AutomationControlled,WebGPU" in args


def test_user_data_dir_is_strictly_terminal_argument(temp_env):
    launcher: OrbitaLauncher = temp_env["launcher"]
    profile_dir = temp_env["tmp_path"] / "prof_terminal"

    args = launcher.build_launch_args(
        user_data_dir=profile_dir,
        start_url="https://www.tiktok.com",
    )

    expected_flag = f"--user-data-dir={profile_dir.resolve()}"
    assert args[-1] == expected_flag, "ANTIDETECT_MASTER_SPEC mandates --user-data-dir as the very last argument."


def test_authenticated_proxy_preferences_injection(temp_env):
    launcher: OrbitaLauncher = temp_env["launcher"]
    profile_dir = temp_env["tmp_path"] / "prof_auth_proxy"

    profile_data = {
        "id": 101,
        "name": "TikTokUS_Auth",
        "uuid": "test-uuid-101",
        "canvas_noise": 9.25,
        "webgl_vendor": "Google Inc. (NVIDIA)",
        "webgl_renderer": "ANGLE (NVIDIA, RTX 4090)",
    }
    proxy_data = {
        "host": "185.48.54.7",
        "port": 5327,
        "protocol": "socks5",
        "username": "secret_user",
        "password": "secret_password_123",
    }

    # Prepare environment
    launcher.prepare_profile_environment(profile_dir, profile_data, proxy_data)

    pref_path = profile_dir / "Default" / "Preferences"
    assert pref_path.exists(), "Default/Preferences file must be created"

    data = json.loads(pref_path.read_text(encoding="utf-8"))
    assert data["profile"]["exit_type"] == "Normal"
    assert data["signin"]["allowed"] is False
    assert data["sync"]["requested"] is False

    gologin = data.get("gologin", {})
    assert gologin["name"] == "TikTokUS_Auth"
    assert gologin["canvasMode"] == "noise"
    # Fingerprint values come from the profile's own fingerprint (here derived from its uuid), never from
    # loose legacy columns, which held values shared by many profiles.
    expected_fp = generate_fingerprint("test-uuid-101")
    assert gologin["canvasNoise"] == expected_fp["canvas_noise"]
    assert gologin["webrtc"]["enable"] is False
    assert gologin["webrtc"]["mode"] == "disabled"
    assert gologin["webgl"]["metadata"]["vendor"] == expected_fp["webgl"]["vendor"]

    # Verify proxy authentication payload in Preferences
    proxy_conf = gologin.get("proxy", {})
    assert proxy_conf["mode"] == "fixed_servers"
    assert proxy_conf["username"] == "secret_user"
    assert proxy_conf["password"] == "secret_password_123"
    assert proxy_conf["server"] == "socks5://secret_user:secret_password_123@185.48.54.7:5327"
    assert proxy_conf["schema"] == "socks5"


def test_no_credential_leakage_in_command_line_args(temp_env):
    launcher: OrbitaLauncher = temp_env["launcher"]
    profile_dir = temp_env["tmp_path"] / "prof_cli_leak"

    proxy_uri = "http://super_secret_user:super_secret_pass@185.48.54.7:8080"
    args = launcher.build_launch_args(
        user_data_dir=profile_dir,
        proxy_uri=proxy_uri,
    )

    args_str = " ".join(args)
    # The password and username MUST NOT appear in CLI arguments
    assert "super_secret_user" not in args_str
    assert "super_secret_pass" not in args_str
    # Only clean host:port should appear in CLI proxy flag if passed
    assert "--proxy-server=http://185.48.54.7:8080" in args


def test_pre_launch_sanitization_removes_locks(temp_env):
    launcher: OrbitaLauncher = temp_env["launcher"]
    profile_dir = temp_env["tmp_path"] / "prof_sanitize"
    profile_dir.mkdir(parents=True, exist_ok=True)

    # Simulate abandoned lock files from previous crashed session
    (profile_dir / "SingletonLock").write_text("12345", encoding="utf-8")
    (profile_dir / "SingletonSocket").write_text("sock", encoding="utf-8")
    (profile_dir / "RunningChromeVersion").write_text("130.0", encoding="utf-8")

    sync_dir = profile_dir / "Default" / "Sync Data"
    sync_dir.mkdir(parents=True, exist_ok=True)
    (sync_dir / "data.bin").write_text("stale", encoding="utf-8")

    # Call prepare_profile_environment
    launcher.prepare_profile_environment(profile_dir, {"name": "TestClean"}, None)

    # All lock files and Sync Data must be wiped
    assert not (profile_dir / "SingletonLock").exists()
    assert not (profile_dir / "SingletonSocket").exists()
    assert not (profile_dir / "RunningChromeVersion").exists()
    assert not sync_dir.exists()


def test_network_leak_policy_quarantines_leaked_proxy(temp_env):
    proxy_repo: ProxyRepository = temp_env["proxy_repo"]

    # Create a proxy in DB
    px_id = proxy_repo.create(
        host="192.168.1.100",
        port=8080,
        protocol="http",
    )

    # In our test fixture, leak_policy has 192.168.1.100 in disallowed_ips
    # When evaluated, leak_policy detects the leak
    policy = temp_env["proxy_service"].leak_policy
    verdict = policy.evaluate("192.168.1.100")
    assert verdict.leak_detected is True
    assert "Critical IP Leak Detected" in verdict.reason

    # Verify repo records leak
    proxy_repo.mark_ip_leak(px_id, error_msg=verdict.reason)
    row = proxy_repo.get_by_id(px_id)
    assert row["status"] == "leak_detected"
    assert "leak" in row["error_message"].lower()


def test_daemon_profile_proxy_synchronization(temp_env, monkeypatch):
    launcher: OrbitaLauncher = temp_env["launcher"]
    fake_daemon_dir = temp_env["tmp_path"] / "fake_daemon_profiles"
    fake_uuid_dir = fake_daemon_dir / "test-daemon-uuid"
    fake_default = fake_uuid_dir / "Default"
    fake_default.mkdir(parents=True, exist_ok=True)
    fake_pref = fake_default / "Preferences"
    fake_pref.write_text(json.dumps({"gologin": {"proxy": {"mode": "none"}}}), encoding="utf-8")

    # Monkeypatch DAEMON_PROFILES_DIR
    monkeypatch.setattr(launcher, "DAEMON_PROFILES_DIR", fake_daemon_dir)

    proxy_data = {
        "host": "45.12.33.11",
        "port": 1080,
        "protocol": "socks5",
        "username": "daemon_user",
        "password": "daemon_pass",
    }

    launcher.sync_daemon_profile_proxy("test-daemon-uuid", proxy_data)

    updated_data = json.loads(fake_pref.read_text(encoding="utf-8"))
    updated_proxy = updated_data["gologin"]["proxy"]
    assert updated_proxy["mode"] == "fixed_servers"
    assert updated_proxy["username"] == "daemon_user"
    assert updated_proxy["server"] == "socks5://daemon_user:daemon_pass@45.12.33.11:1080"
