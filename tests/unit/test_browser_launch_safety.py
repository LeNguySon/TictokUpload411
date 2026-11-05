"""Browser management audit: launch lifecycle & host-IP protection (defensive only).

1. --host-resolver-rules carried literal quotes (list args never go through a shell), so Chromium
   received an invalid rule and the DNS-leak guard was inactive.
2. A profile with no proxy and no VPN was launched straight from the host IP.
3. If the WireGuard bridge failed to start, the browser was launched anyway WITHOUT a proxy.
4. The bridge ran in mock mode in production: it only reserved a port, so VPN profiles never had
   network; the real bridge needs a configured binary and must fail closed without one.
5. The launch worker launched profiles with no proxy, a leak_detected proxy, or a dead proxy
   (its "pre-launch guard" only logged a warning).
6. The real bridge left the WireGuard config (private key) in %TEMP% and never drained its pipes.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from src.infrastructure.browser.orbita_launcher import OrbitaLauncher

WG_CONF = """[Interface]
PrivateKey = cGFzc3dvcmRwYXNzd29yZHBhc3N3b3JkcGFzc3dvcmQ=
Address = 10.64.0.2/32
DNS = 10.64.0.1

[Peer]
PublicKey = cHVibGljcHVibGljcHVibGljcHVibGljcHVibGljcHU=
Endpoint = 185.48.54.7:51820
AllowedIPs = 0.0.0.0/0
"""


@pytest.fixture
def launcher(tmp_path: Path) -> OrbitaLauncher:
    return OrbitaLauncher(executable_path=tmp_path / "chrome.exe")


def _profile(tmp_path: Path, **extra) -> dict:
    return {"id": 501, "name": "Safe", "storage_dir": str(tmp_path / "p501"), **extra}


def test_host_resolver_rules_has_no_literal_quotes(launcher, tmp_path):
    args = launcher.build_launch_args(tmp_path / "d", proxy_uri="http://u:p@185.48.54.7:8080")
    rule = [a for a in args if a.startswith("--host-resolver-rules=")]
    assert rule == ["--host-resolver-rules=MAP * 0.0.0.0 , EXCLUDE 185.48.54.7"]


def test_launch_without_proxy_or_vpn_is_refused(launcher, tmp_path):
    with patch("subprocess.Popen", side_effect=AssertionError("browser started from the host IP")):
        with pytest.raises(PermissionError):
            launcher.launch_profile(_profile(tmp_path))


def test_vpn_bridge_failure_never_falls_back_to_direct(launcher, tmp_path):
    with (
        patch("src.infrastructure.vpn.vpn_bridge.UserspaceVpnBridge.start", side_effect=FileNotFoundError("no binary")),
        patch("subprocess.Popen", side_effect=AssertionError("browser started without the VPN")),
    ):
        with pytest.raises(RuntimeError):
            launcher.launch_profile(_profile(tmp_path, vpn_config=WG_CONF))
    assert 501 not in launcher.vpn_bridges


def test_vpn_bridge_is_real_not_mock(launcher, tmp_path):
    created = {}
    real_init = __import__(
        "src.infrastructure.vpn.vpn_bridge", fromlist=["UserspaceVpnBridge"]
    ).UserspaceVpnBridge.__init__

    def spy_init(self, *args, **kwargs):
        created.update(kwargs)
        real_init(self, *args, **kwargs)

    with (
        patch("src.infrastructure.vpn.vpn_bridge.UserspaceVpnBridge.__init__", spy_init),
        patch("src.infrastructure.vpn.vpn_bridge.UserspaceVpnBridge.start", side_effect=FileNotFoundError("x")),
    ):
        with pytest.raises(RuntimeError):
            launcher.launch_profile(_profile(tmp_path, vpn_config=WG_CONF))
    assert created.get("mock_mode", False) is False


def test_real_bridge_removes_private_key_file_and_does_not_pipe(tmp_path, monkeypatch):
    from src.infrastructure.vpn import vpn_bridge as mod
    from src.infrastructure.vpn.wireguard_manager import WireGuardConfig

    binary = tmp_path / "wireproxy.exe"
    binary.write_bytes(b"x")
    monkeypatch.setenv("TEMP", str(tmp_path))
    popen_kwargs = {}

    def fake_popen(cmd, **kwargs):
        popen_kwargs.update(kwargs)
        return MagicMock()

    bridge = mod.UserspaceVpnBridge(
        profile_id=7, config=WireGuardConfig.from_conf(WG_CONF, name="wg7"), binary_path=binary
    )
    with (
        patch.object(mod.subprocess, "Popen", side_effect=fake_popen),
        patch.object(mod.UserspaceVpnBridge, "_check_port_open", return_value=True),
    ):
        bridge.start()
    try:
        assert not list(tmp_path.glob("wg_7*.conf")), "WireGuard private key must not stay on disk"
        assert popen_kwargs.get("stdout") is subprocess.DEVNULL and popen_kwargs.get("stderr") is subprocess.DEVNULL
    finally:
        bridge.stop()


# ---------------------------------------------------------------- launch worker gate
def _worker(profile: dict, proxy: dict | None, alive: bool = True):
    from src.application.workers.orbita_launch_worker import OrbitaLaunchWorker

    profile_repo, proxy_repo, launcher = MagicMock(), MagicMock(), MagicMock()
    profile_repo.get_by_id.return_value = profile
    proxy_repo.get_by_id.return_value = proxy
    worker = OrbitaLaunchWorker([profile["id"]], profile_repo, proxy_repo, orbita_launcher=launcher)
    failed: list = []
    worker.signals.profile_failed.connect(lambda *a: failed.append(a))
    with patch.object(type(worker), "_check_proxy_alive", return_value=alive):
        worker.run()
    return launcher, failed


@pytest.mark.parametrize(
    ("profile", "proxy", "alive"),
    [
        ({"id": 1, "name": "NoProxy", "uuid": "u1"}, None, True),
        (
            {"id": 2, "name": "Leak", "uuid": "u2", "proxy_id": 9},
            {"id": 9, "host": "1.2.3.4", "port": 80, "status": "leak_detected"},
            True,
        ),
        (
            {"id": 3, "name": "Dead", "uuid": "u3", "proxy_id": 9},
            {"id": 9, "host": "1.2.3.4", "port": 80, "status": "active"},
            False,
        ),
    ],
)
def test_launch_worker_refuses_unsafe_profiles(qapp, profile, proxy, alive):
    launcher, failed = _worker(profile, proxy, alive)
    launcher.launch_via_gologin_sdk.assert_not_called()
    launcher.launch_profile.assert_not_called()
    assert failed and failed[0][0] == profile["id"]


def test_launch_worker_allows_vpn_profile_without_proxy(qapp):
    launcher, failed = _worker({"id": 4, "name": "Vpn", "uuid": "u4", "vpn_config": WG_CONF}, None, True)
    assert launcher.launch_via_gologin_sdk.called or launcher.launch_profile.called


@pytest.fixture
def qapp():
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])
