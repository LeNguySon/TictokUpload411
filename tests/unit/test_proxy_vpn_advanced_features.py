"""
Unit & TDD Test Suite for Advanced Proxy, WireGuard VPN & Antidetect Hardening.
Tests:
1. ProfileTableWidget renders '🛡️ WireGuard VPN' and '🔄 Rotating Proxy' correctly in columns 4 & 5.
2. Context menu signals: remove_proxy_requested, rotate_proxy_requested, check_proxy_requested.
3. MainWindow handlers:
   - _on_remove_proxy_selected removes both proxy_id and vpn_config.
   - _on_rotate_proxy_selected calls proxy_service.change_rotating_ip.
   - _check_proxy_alive detects dead / live proxy hosts.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.infrastructure.database.migrations.runner import run_all_migrations
from src.infrastructure.database.repositories.profile_repository import ProfileRepository
from src.infrastructure.database.repositories.proxy_repository import ProxyRepository
from src.presentation.views.main_window import TikTokManagerMainWindow
from src.presentation.widgets.profile_table_widget import ProfileTableWidget


def test_profile_table_renders_wireguard_and_rotating_proxy_columns(qapp):
    table = ProfileTableWidget()

    profiles = [
        # Profile 1: Uses WireGuard VPN
        {
            "id": 1,
            "name": "Prof_WG",
            "vpn_config": "[Interface]\nPrivateKey = ...\n[Peer]\nEndpoint = 1.2.3.4:51820",
            "proxy_id": None,
        },
        # Profile 2: Uses Rotating Proxy
        {
            "id": 2,
            "name": "Prof_Rotating",
            "proxy_host": "103.20.5.10",
            "proxy_port": 8080,
            "proxy_type": "rotating",
            "change_ip_url": "https://rotate.proxy.com/api/change",
        },
        # Profile 3: Uses Standard Static Proxy
        {
            "id": 3,
            "name": "Prof_Static",
            "proxy_host": "142.250.190.46",
            "proxy_port": 3128,
            "proxy_type": "static",
        },
    ]

    table.load_profiles(profiles)

    # Row 0: WireGuard VPN
    col4_text_0 = table.item(0, 4).text()
    col5_text_0 = table.item(0, 5).text()
    assert "WireGuard" in col4_text_0
    assert "🛡️" in col4_text_0
    assert col5_text_0 == "WireGuard"

    # Row 1: Rotating Proxy
    col4_text_1 = table.item(1, 4).text()
    col5_text_1 = table.item(1, 5).text()
    assert "103.20.5.10:8080" in col4_text_1
    assert "🔄" in col4_text_1
    assert col5_text_1 == "rotating"

    # Row 2: Standard Static Proxy
    col4_text_2 = table.item(2, 4).text()
    col5_text_2 = table.item(2, 5).text()
    assert col4_text_2 == "142.250.190.46:3128"
    assert "🔄" not in col4_text_2
    assert col5_text_2 == "http"


def test_profile_table_has_proxy_vpn_advanced_signals(qapp):
    table = ProfileTableWidget()
    assert hasattr(table, "remove_proxy_requested")
    assert hasattr(table, "rotate_proxy_requested")
    assert hasattr(table, "check_proxy_requested")


def test_main_window_remove_proxy_and_vpn_action(qapp, tmp_path: Path):
    db_file = tmp_path / "test_mw_proxy_vpn.db"
    run_all_migrations(db_file)

    profile_repo = ProfileRepository(db_file)
    proxy_repo = ProxyRepository(db_file)

    px_id = proxy_repo.create(host="1.1.1.1", port=8080)
    p_id = profile_repo.create(
        {
            "name": "ProfToWipe",
            "proxy_id": px_id,
            "vpn_config": "[Interface]\nPrivateKey = ...",
        }
    )

    with patch("src.infrastructure.browser.sammonny_daemon_manager.SamMonnyDaemonSupervisor.ensure_daemon_running"):
        mw = TikTokManagerMainWindow(db_path=db_file)

    # Trigger remove proxy/vpn action
    mw._on_remove_proxy_selected([p_id])

    updated = profile_repo.get_by_id(p_id)
    assert updated["proxy_id"] is None
    assert updated["vpn_config"] is None


def test_main_window_rotate_proxy_ip_action(qapp, qtbot, tmp_path: Path):
    db_file = tmp_path / "test_mw_rotate.db"
    run_all_migrations(db_file)

    profile_repo = ProfileRepository(db_file)
    proxy_repo = ProxyRepository(db_file)

    px_id = proxy_repo.create(
        host="103.20.5.10",
        port=8080,
        proxy_type="rotating",
        change_ip_url="https://rotate.link/change",
    )
    p_id = profile_repo.create(
        {
            "name": "ProfRotating",
            "proxy_id": px_id,
        }
    )

    with patch("src.infrastructure.browser.sammonny_daemon_manager.SamMonnyDaemonSupervisor.ensure_daemon_running"):
        mw = TikTokManagerMainWindow(db_path=db_file)

    # Mock proxy_service.change_rotating_ip
    mw.proxy_service.change_rotating_ip = MagicMock(return_value=True)

    mw._on_rotate_proxy_selected([p_id])

    # Rotation (HTTP) runs on the UI pool since UI responsiveness T7.
    qtbot.waitUntil(lambda: mw.proxy_service.change_rotating_ip.called, timeout=5000)
    mw.proxy_service.change_rotating_ip.assert_called_once_with(px_id)


def test_pre_launch_proxy_guard_detects_dead_proxy(qapp, tmp_path: Path):
    db_file = tmp_path / "test_mw_guard.db"
    run_all_migrations(db_file)

    with patch("src.infrastructure.browser.sammonny_daemon_manager.SamMonnyDaemonSupervisor.ensure_daemon_running"):
        mw = TikTokManagerMainWindow(db_path=db_file)

    # Non-existent localhost port should be dead
    dead_proxy = {"host": "127.0.0.1", "port": 59999}
    assert mw._check_proxy_alive(dead_proxy) is False

    # Mock alive proxy
    with patch("socket.create_connection"):
        alive_proxy = {"host": "1.1.1.1", "port": 8080}
        assert mw._check_proxy_alive(alive_proxy) is True
